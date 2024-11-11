import pandas as pd
import csv
from typing import List, Dict, Union, Iterator
from pathlib import Path
import asyncio
import aiohttp
from urllib.parse import urlparse
import logging
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from tqdm.asyncio import tqdm
import tempfile
import os

@dataclass
class BatchProcessingResult:
    url: str
    status: str
    downloaded_files: Dict[str, List[str]]
    parsed_content: str
    error: str = None

class BatchURLProcessor:
    """Handles batch processing of URLs from various file formats."""
    
    SUPPORTED_FORMATS = {'.txt', '.csv', '.xlsx', '.xls', '.json'}
    
    def __init__(self, 
                 scraper,
                 parser,
                 doc_downloader,
                 max_concurrent: int = 5,
                 timeout: int = 30):
        self.scraper = scraper
        self.parser = parser
        self.doc_downloader = doc_downloader
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def _read_txt(self, file_path: Path) -> Iterator[str]:
        """Read URLs from a text file."""
        with open(file_path, 'r') as f:
            for line in f:
                url = line.strip()
                if url and not url.startswith('#'):
                    yield url
    
    def _read_csv(self, file_path: Path) -> Iterator[str]:
        """Read URLs from a CSV file."""
        try:
            df = pd.read_csv(file_path)
            # Try to find column containing URLs
            url_columns = [col for col in df.columns 
                         if any(u in col.lower() for u in ['url', 'link', 'website'])]
            if url_columns:
                return df[url_columns[0]].dropna().unique()
            else:
                # If no clear URL column, try first column
                return df.iloc[:, 0].dropna().unique()
        except Exception as e:
            self.logger.error(f"Error reading CSV file: {str(e)}")
            return iter([])
    
    def _read_excel(self, file_path: Path) -> Iterator[str]:
        """Read URLs from an Excel file."""
        try:
            df = pd.read_excel(file_path)
            url_columns = [col for col in df.columns 
                         if any(u in col.lower() for u in ['url', 'link', 'website'])]
            if url_columns:
                return df[url_columns[0]].dropna().unique()
            else:
                return df.iloc[:, 0].dropna().unique()
        except Exception as e:
            self.logger.error(f"Error reading Excel file: {str(e)}")
            return iter([])
    
    def _read_json(self, file_path: Path) -> Iterator[str]:
        """Read URLs from a JSON file."""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            if isinstance(data, list):
                # If it's a list of strings
                if all(isinstance(item, str) for item in data):
                    return iter(data)
                # If it's a list of dicts
                elif all(isinstance(item, dict) for item in data):
                    url_keys = [k for k in data[0].keys() 
                              if any(u in k.lower() for u in ['url', 'link', 'website'])]
                    if url_keys:
                        return iter(item[url_keys[0]] for item in data if url_keys[0] in item)
            return iter([])
        except Exception as e:
            self.logger.error(f"Error reading JSON file: {str(e)}")
            return iter([])
    
    def read_urls(self, file_path: Union[str, Path]) -> Iterator[str]:
        """Read URLs from supported file formats."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        if file_path.suffix.lower() not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported file format. Supported formats: {self.SUPPORTED_FORMATS}")
        
        # Choose appropriate reader based on file extension
        readers = {
            '.txt': self._read_txt,
            '.csv': self._read_csv,
            '.xlsx': self._read_excel,
            '.xls': self._read_excel,
            '.json': self._read_json
        }
        
        reader = readers.get(file_path.suffix.lower())
        if reader:
            yield from reader(file_path)
    
    async def process_url(self, url: str, session: aiohttp.ClientSession) -> BatchProcessingResult:
        """Process a single URL asynchronously."""
        try:
            # Create temp directory for this URL's downloads
            url_temp_dir = tempfile.mkdtemp()
            
            # Scrape the page
            scraped_data = await self.scraper.scrape_page_async(url, session)
            
            if not scraped_data:
                return BatchProcessingResult(
                    url=url,
                    status='failed',
                    downloaded_files={},
                    parsed_content='',
                    error='Failed to scrape page'
                )
            
            # Extract and clean content
            body_content = self.scraper.extract_body_content(scraped_data)
            cleaned_content = self.scraper.clean_body_content(body_content)
            
            # Initialize document downloader for this URL
            url_doc_downloader = self.doc_downloader(url, url_temp_dir)
            
            # Find and download documents
            doc_links = url_doc_downloader.find_document_links(scraped_data)
            downloaded_files = {}
            
            if doc_links:
                downloaded_files = await url_doc_downloader.download_documents_async(doc_links, session)
            
            # Parse content
            split_content = self.scraper.split_dom_content(cleaned_content)
            parsed_content = await self.parser.parse_with_ollama_async(split_content)
            
            return BatchProcessingResult(
                url=url,
                status='success',
                downloaded_files=downloaded_files,
                parsed_content=parsed_content
            )
            
        except Exception as e:
            return BatchProcessingResult(
                url=url,
                status='error',
                downloaded_files={},
                parsed_content='',
                error=str(e)
            )
    
    async def process_urls_async(self, urls: List[str]) -> List[BatchProcessingResult]:
        """Process multiple URLs asynchronously."""
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            tasks = []
            for url in urls:
                task = asyncio.ensure_future(self.process_url(url, session))
                tasks.append(task)
            
            # Process URLs with progress bar
            results = []
            for f in tqdm.as_completed(tasks, total=len(tasks), desc="Processing URLs"):
                results.append(await f)
            
            return results
    
    def process_file(self, file_path: Union[str, Path]) -> List[BatchProcessingResult]:
        """Process all URLs from a file."""
        urls = list(self.read_urls(file_path))
        if not urls:
            raise ValueError("No valid URLs found in the file")
        
        return asyncio.run(self.process_urls_async(urls))
    
    def export_results(self, results: List[BatchProcessingResult], 
                      output_dir: Union[str, Path]) -> Dict[str, str]:
        """Export processing results to files."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create summary report
        summary = {
            'total_urls': len(results),
            'successful': len([r for r in results if r.status == 'success']),
            'failed': len([r for r in results if r.status != 'success']),
            'urls': [{
                'url': r.url,
                'status': r.status,
                'error': r.error,
                'files_downloaded': sum(len(files) for files in r.downloaded_files.values())
            } for r in results]
        }
        
        # Save summary report
        summary_path = output_dir / 'summary.json'
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Save detailed results
        results_path = output_dir / 'results.json'
        detailed_results = [{
            'url': r.url,
            'status': r.status,
            'error': r.error,
            'downloaded_files': r.downloaded_files,
            'parsed_content': r.parsed_content
        } for r in results]
        
        with open(results_path, 'w') as f:
            json.dump(detailed_results, f, indent=2)
        
        return {
            'summary': str(summary_path),
            'details': str(results_path)
        }
