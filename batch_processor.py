# batch_processor.py
import pandas as pd
import asyncio
import aiohttp
from typing import List, Dict, Any, Tuple, Optional, Iterator
from pathlib import Path
import logging
import json
from dataclasses import dataclass

@dataclass
class BatchProcessingResult:
    """Stores results from batch processing operations"""
    url: str
    status: str
    downloaded_files: Dict[str, List[str]]
    parsed_content: str
    raw_content: str
    error: Optional[str] = None
    model_number: Optional[str] = None

class BatchURLProcessor:
    """Handles batch processing of URLs from various file formats."""
    
    SUPPORTED_FORMATS = {'.txt', '.csv', '.xlsx', '.xls', '.json'}
    
    def __init__(self, 
                 unified_parser,
                 max_concurrent: int = 5,
                 timeout: int = 30,
                 result_manager=None,
                 default_model_number: Optional[str] = None):
        """Initialize processor with unified parser and configurations."""
        self.parser = unified_parser
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.result_manager = result_manager
        self.default_model_number = default_model_number
        self.logger = logging.getLogger(__name__)

    def read_urls(self, file_path: str) -> Iterator[Tuple[str, str]]:
        """Read URLs from supported file formats."""
        suffix = Path(file_path).suffix.lower()
        
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported file format: {suffix}")
        
        if suffix == '.txt':
            with open(file_path, 'r') as f:
                return [(self.default_model_number, line.strip()) for line in f if line.strip()]
        
        elif suffix == '.csv':
            df = pd.read_csv(file_path)
            if 'Model Number' in df.columns and 'URL' in df.columns:
                return list(zip(df['Model Number'], df['URL']))
            elif 'URL' in df.columns:
                return [(self.default_model_number, url) for url in df['URL']]
            else:
                raise ValueError("CSV must contain 'URL' column")
        
        elif suffix in {'.xlsx', '.xls'}:
            df = pd.read_excel(file_path)
            if 'Model Number' in df.columns and 'URL' in df.columns:
                return list(zip(df['Model Number'], df['URL']))
            elif 'URL' in df.columns:
                return [(self.default_model_number, url) for url in df['URL']]
            else:
                raise ValueError("Excel file must contain 'URL' column")
        
        elif suffix == '.json':
            with open(file_path, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [(item.get('model_number', self.default_model_number), 
                            item['url']) for item in data]
                else:
                    raise ValueError("JSON must contain a list of objects with 'url' field")

    async def process_url(self, model_number: str, url: str, 
                         session: aiohttp.ClientSession) -> BatchProcessingResult:
        """Process a single URL with complete parsing and analysis"""
        try:
            # Generate unique site ID
            site_id = f"batch_{model_number}_{hash(url)}"
            
            # Parse website asynchronously using UnifiedParser
            parse_result = await self.parser.parse_website_async(
                site_id=site_id,
                url=url,
                parse_description="general",
                session=session
            )
            
            # Save results if result manager is available
            if self.result_manager:
                try:
                    self.result_manager.save_results(
                        model_number=model_number,
                        url=url,
                        raw_content=parse_result.raw_content,
                        site_id=site_id,
                        image_matches=parse_result.image_matches if hasattr(parse_result, 'image_matches') else [],
                        pdf_links=parse_result.pdf_links if hasattr(parse_result, 'pdf_links') else [],
                        parsed_content=parse_result.content_analysis if hasattr(parse_result, 'content_analysis') else {}
                    )
                except Exception as e:
                    self.logger.error(f"Failed to save results for {url}: {str(e)}")
            
            return BatchProcessingResult(
                url=url,
                status='success',
                downloaded_files={
                    'images': parse_result.downloaded_files or [],
                    'pdfs': parse_result.pdf_links if hasattr(parse_result, 'pdf_links') else []
                },
                parsed_content=parse_result.content_analysis if hasattr(parse_result, 'content_analysis') else {},
                raw_content=parse_result.raw_content,
                model_number=model_number
            )
            
        except Exception as e:
            self.logger.error(f"Error processing URL {url}: {str(e)}")
            return BatchProcessingResult(
                url=url,
                status='error',
                downloaded_files={},
                parsed_content='',
                raw_content='',
                error=str(e),
                model_number=model_number
            )