
# parse.py
import json
from urllib.parse import urlparse
from langchain_google_genai import ChatGoogleGenerativeAI
import google.generativeai as genai
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from typing import Optional, List, Dict, Union
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import aiofiles

from utils.api_limiting import rate_limit
from utils.parse_config import ParserConfig
from utils.url_validator import URLValidator
from utils.parse_result import ParseResult

from content_analyzer import ContentAnalyzer, ImageMatch
from unified_scraper import UnifiedScraper
from site_scraper import SiteScraper
from loader import ImageLoader
from batch_processor import BatchURLProcessor, BatchProcessingResult
from doc_downloader import DocumentDownloader
from result_manager import CSVResultManager


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UnifiedParser:
    def __init__(self, config: ParserConfig, image_loader=None):
        """Initialize the UnifiedParser with configurations loaded from YAML and .env"""
        # Initialize Gemini
        genai.configure(api_key=config.api_key)
        self.model = ChatGoogleGenerativeAI(model=config.model_name)
        
        # Initialize other components
        self.config = config
        self.content_analyzer = ContentAnalyzer(api_key=config.api_key, data_dir=config.data_dir)
        self.site_scraper = SiteScraper(download_dir=config.data_dir)
        self.image_loader = image_loader or ImageLoader() # Default to ImageLoader() if not provided
        self.result_manager = CSVResultManager(config.data_dir)
        
        self.data_dir = config.data_dir
        self.results_dir = os.path.join(config.data_dir, "parse_results")
        os.makedirs(self.results_dir, exist_ok=True)
        
        self.doc_downloader = DocumentDownloader(
        base_url="",  # Will be set during parsing
        download_dir=config.data_dir
        )

        # Updated prompt template that handles both structured and free-form queries
        self.prompt = ChatPromptTemplate.from_template(
            """
            Analyze the following website content and extract relevant information based on the query.
            
            Website Content: {dom_content}
            
            Query: {parse_description}
            
            For product information queries, include details about:
            - Product name
            - Model number
            - Serial number
            - Warranty information
            - User manuals (with URLs if available)
            - Other relevant documents (with URLs if available)
            
            For other queries:
            - Provide relevant information from the content
            - Include specific data points when found
            - Return document/image URLs when relevant
            - Indicate if information is not found
            
            Please provide the information in a clear, structured format.
            """
        )


    def parse_website(
            self,
            url: str,
            min_confidence: float = 0.7,
            show_all_images: bool = False,
            parse_description: Optional[str] = None,
            model_number: Optional[str] = None,  # Add model_number parameter
            **kwargs
        ) -> ParseResult:
        """Parse a website using both Gemini and ContentAnalyzer capabilities"""
        
        try:
            
            # Validate and normalize the URL
            if not URLValidator.is_valid_url(url):
                raise ValueError(f"Invalid URL: {url}")
            
            normalized_url = URLValidator.normalize_url(url)
            # Create site-specific folder
            site_dir = self.site_scraper.create_site_folder(url)
            site_id = os.path.basename(site_dir)
            
            # Step 2: Scrape the webpage using UnifiedScraper
            logger.info(f"Scraping website: {url}")
            unified_scraper = UnifiedScraper()
            html_content = unified_scraper.scrape_website(url)
            if not html_content:
                raise Exception("Failed to scrape website")
            
            # Step 3: Clean the content using UnifiedScraper's cleaning method
            logger.info("Cleaning content using UnifiedScraper")
            cleaned_content = unified_scraper.clean_content(html_content)
            
            # Extract images
            logger.info("Extracting images from website")
            images = self.site_scraper.extract_images(html_content, url)
            image_urls = [
                URLValidator.resolve_relative_url(normalized_url, img['url']) for img in images
            ]
            
            # Download images
            downloaded_images = self.image_loader.download_images_from_html(html_content, normalized_url)
            downloaded_files = [path[1] for path in downloaded_images] if downloaded_images else []
            
            # Store the base URL for relative link resolution
            self.site_scraper.base_url = url
        
            # Find document links (PDF/DOCX)
            logger.info("Finding PDF and DOCX documents")
            document_links = self.find_pdf_links(html_content)
            logger.info(f"Found {len(document_links)} documents: {document_links}")
            
            # Analyze content
            logger.info("Analyzing website content")
            content_analysis = self.content_analyzer.analyze_content(cleaned_content)
            
            # Find matching images based on the show_all_images flag
            logger.info("Finding matching images")
            image_matches = self.content_analyzer.find_matching_images(
                content_analysis=content_analysis,
                available_images=image_urls,
                threshold=(0.0 if show_all_images else min_confidence)
            )
            
            # Perform Gemini parsing if description provided
            gemini_result = None
            if parse_description:
                processed_chunks = self.preprocess_content(cleaned_content)
                gemini_result = self.parse_with_gemini(processed_chunks, parse_description)
            
            # Create parse result
            result = ParseResult(
                site_id=site_id,
                content_analysis=content_analysis,
                image_matches=image_matches,
                raw_content=cleaned_content,
                gemini_parse_result=gemini_result,
                downloaded_files=downloaded_files,
                pdf_links=document_links  # Store the document links
            )
            
            # Save results using CSVResultManager if available
            if self.result_manager and model_number:
                self.result_manager.save_result(
                    parse_result=result,
                    model_number=model_number,
                    url=url
                )
            
            # Save JSON results
            self._save_parse_result(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing website: {str(e)}")
            raise
        
    async def parse_website_async(
            self,
            url: str,
            min_confidence: float = 0.7,
            show_all_images: bool = False,
            parse_description: Optional[str] = None,
            model_number: Optional[str] = None,  # Add model_number parameter
            **kwargs
        ) -> ParseResult:
        """Asynchronous version of parse_website"""
        try:
            # Validate and normalize the URL
            if not URLValidator.is_valid_url(url):
                raise ValueError(f"Invalid URL: {url}")
            
            normalized_url = URLValidator.normalize_url(url)
            site_dir = self.site_scraper.create_site_folder(url)
            site_id = os.path.basename(site_dir)
            
            # Scrape website content asynchronously
            unified_scraper = UnifiedScraper()
            html_content = await unified_scraper.scrape_website_async(url)
            if not html_content:
                raise Exception("Failed to scrape website")
            
            # Process content and create result
            cleaned_content = unified_scraper.clean_content(html_content)
            images = self.site_scraper.extract_images(html_content, url)
            image_urls = [
                URLValidator.resolve_relative_url(normalized_url, img['url']) 
                for img in images
            ]
            
            # Download images asynchronously
            downloaded_images = await self.image_loader.download_images_async(
                image_urls, 
                normalized_url
            )
            downloaded_files = [path[1] for path in downloaded_images] if downloaded_images else []
            
            self.site_scraper.base_url = url
            document_links = self.find_pdf_links(html_content)
            content_analysis = self.content_analyzer.analyze_content(cleaned_content)
            
            image_matches = self.content_analyzer.find_matching_images(
                content_analysis=content_analysis,
                available_images=image_urls,
                threshold=(0.0 if show_all_images else min_confidence)
            )
            
            # Perform Gemini parsing if description provided
            gemini_result = None
            if parse_description:
                processed_chunks = self.preprocess_content(cleaned_content)
                gemini_result = await self.parse_with_gemini_async(processed_chunks, parse_description)
            
            # Create parse result
            result = ParseResult(
                site_id=site_id,
                content_analysis=content_analysis,
                image_matches=image_matches,
                raw_content=cleaned_content,
                gemini_parse_result=gemini_result,
                downloaded_files=downloaded_files,
                pdf_links=document_links
            )
            
            # Save results using CSVResultManager if available
            if self.result_manager and model_number:
                self.result_manager.save_result(
                    parse_result=result,
                    model_number=model_number,
                    url=url
                )
            
            # Save JSON results
            await self._save_parse_result_async(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing website: {str(e)}")
            raise

    def create_batch_processor(
            self, 
            max_concurrent: int = 5, 
            timeout: int = 30,
            model_number: Optional[str] = None
        ) -> BatchURLProcessor:
        """Create a BatchURLProcessor instance with optional model number"""
        return BatchURLProcessor(
            scraper=self.site_scraper,
            parser=self,
            doc_downloader=self.doc_downloader,
            max_concurrent=max_concurrent,
            timeout=timeout,
            result_manager=self.result_manager,
            model_number=model_number
        )

    @rate_limit(calls=10, period=60) # 10 calls per minute
    def parse_with_gemini(self, dom_chunks: List[str], parse_description: str) -> dict:
        """Parse content chunks using Gemini with more flexible response handling"""
        chain = self.prompt | self.model
        found_results = []
        
        is_product_info = any(keyword in parse_description.lower() 
                            for keyword in ['extract product', 'product information', 'product details'])
        
        chunk_size = 3
        for i in range(0, len(dom_chunks), chunk_size):
            chunk_group = " ".join(dom_chunks[i:i + chunk_size])
            try:
                response = chain.invoke({
                    "dom_content": chunk_group,
                    "parse_description": parse_description
                })
                
                # Extract content from response
                if isinstance(response, AIMessage):
                    content = response.content
                elif isinstance(response, str):
                    content = response
                elif hasattr(response, 'content'):
                    content = response.content
                else:
                    logger.warning(f"Unexpected response type: {type(response)}")
                    continue

                content = content.strip()
                
                if not content or content.lower() in ['no match', 'not found', 'no information']:
                    continue

                # Handle product information queries
                if is_product_info:
                    try:
                        # Try to parse as JSON if it looks like JSON
                        if '{' in content and '}' in content:
                            # Extract JSON content if wrapped in code blocks
                            if '```' in content:
                                content = content.split('```')[1].strip()
                                if content.startswith('json'):
                                    content = content[4:].strip()
                            
                            result = json.loads(content)
                            if isinstance(result, dict):
                                # Ensure consistent structure
                                result.setdefault('name', 'NO_MATCH')
                                result.setdefault('model_number', 'NO_MATCH')
                                result.setdefault('serial_number', 'NO_MATCH')
                                result.setdefault('warranty_info', 'NO_MATCH')
                                result.setdefault('user_manual', [])
                                result.setdefault('other_documents', [])
                                
                                # Convert string values to lists where needed
                                for key in ['user_manual', 'other_documents']:
                                    if isinstance(result[key], str) and result[key] != 'NO_MATCH':
                                        result[key] = [result[key]]
                                found_results.append(result)
                        else:
                            # Handle non-JSON product information
                            found_results.append({
                                'raw_content': content,
                                'name': 'NO_MATCH',
                                'model_number': 'NO_MATCH',
                                'serial_number': 'NO_MATCH',
                                'warranty_info': 'NO_MATCH',
                                'user_manual': [],
                                'other_documents': []
                            })
                    except json.JSONDecodeError:
                        # Handle non-JSON content
                        found_results.append({
                            'raw_content': content,
                            'extracted_text': True
                        })
                else:
                    # For non-product queries, collect all relevant information
                    found_results.append(content)

            except Exception as e:
                logger.error(f"Error processing chunk group {i}: {str(e)}")
                continue

        if not found_results:
            return "NO_MATCH"

        if is_product_info:
            # Combine product information results
            combined_results = {
                "name": "NO_MATCH",
                "model_number": "NO_MATCH",
                "serial_number": "NO_MATCH",
                "warranty_info": "NO_MATCH",
                "user_manual": [],
                "other_documents": [],
                "additional_info": []
            }

            for result in found_results:
                if 'raw_content' in result:
                    combined_results['additional_info'].append(result['raw_content'])
                    continue
                    
                for key, value in result.items():
                    if key in ["user_manual", "other_documents"]:
                        if isinstance(value, list):
                            combined_results[key].extend(value)
                        elif value != "NO_MATCH":
                            combined_results[key].append(value)
                    elif key != 'additional_info':
                        if value != "NO_MATCH" and combined_results[key] == "NO_MATCH":
                            combined_results[key] = value

            # Remove duplicates while preserving order
            for key in ["user_manual", "other_documents", "additional_info"]:
                combined_results[key] = list(dict.fromkeys(combined_results[key]))
            
            return combined_results
        else:
            # For non-product queries, combine and return all relevant information
            combined_content = "\n".join(found_results)
            return combined_content if combined_content else "NO_MATCH"
    
    # Add this method to UnifiedParser
    async def download_documents(self, doc_links: List[str], site_id: str) -> Dict[str, List[str]]:
        """Download documents for a specific site"""
        try:
            # Create site-specific document directory
            doc_dir = os.path.join(self.data_dir, site_id, "documents")
            os.makedirs(doc_dir, exist_ok=True)
            
            # Update doc_downloader configuration
            self.doc_downloader.base_url = self.site_scraper.base_url
            self.doc_downloader.download_dir = doc_dir
            
            async with aiohttp.ClientSession() as session:
                downloaded_files = await self.doc_downloader.download_documents_async(
                    doc_links=doc_links,
                    session=session
                )
                
            return downloaded_files
        except Exception as e:
            logger.error(f"Error downloading documents: {str(e)}")
            return {}
    
    async def parse_with_gemini_async(self, dom_chunks: List[str], parse_description: str) -> Union[Dict, str]:
        """Asynchronous version of parse_with_gemini with support for both product info and free-form queries"""
        found_results = []
        chunk_size = 3

        # Determine if this is a product information extraction request
        is_product_info = any(keyword in parse_description.lower() 
                            for keyword in ['extract product', 'product information', 'product details'])

        async def process_chunk(chunk_group: str) -> Union[Dict, str, None]:
            try:
                response = await self.model.agenerate(
                    messages=[{
                        "role": "user",
                        "content": self.prompt.format(
                            dom_content=chunk_group,
                            parse_description=parse_description
                        )
                    }]
                )

                if not response.generations:
                    return None

                content = response.generations[0].text.strip()
                if not content or content == 'NO_MATCH':
                    return None

                if is_product_info:
                    try:
                        # Handle potential JSON formatting
                        if content.startswith('```json'):
                            content = content.split('```json')[1].split('```')[0].strip()
                        elif content.startswith('```'):
                            content = content.split('```')[1].strip()

                        result_json = json.loads(content)
                        if isinstance(result_json, dict):
                            # Ensure proper structure for product info
                            if 'user_manual' in result_json:
                                if not isinstance(result_json['user_manual'], list):
                                    result_json['user_manual'] = ([result_json['user_manual']] 
                                                                if result_json['user_manual'] != 'NO_MATCH' 
                                                                else [])
                            else:
                                result_json['user_manual'] = []

                            if 'other_documents' in result_json:
                                if not isinstance(result_json['other_documents'], list):
                                    result_json['other_documents'] = ([result_json['other_documents']] 
                                                                    if result_json['other_documents'] != 'NO_MATCH' 
                                                                    else [])
                            else:
                                result_json['other_documents'] = []

                            return result_json
                    except json.JSONDecodeError as e:
                        logger.error(f"Error decoding JSON: {e}. Raw string: {content}")
                        return None
                else:
                    # For non-product queries, return the content directly
                    return content if content != 'NO_MATCH' else None

            except Exception as e:
                logger.error(f"Error processing chunk: {str(e)}")
                return None

        # Create tasks for all chunks
        tasks = [process_chunk(" ".join(dom_chunks[i:i + chunk_size])) 
                for i in range(0, len(dom_chunks), chunk_size)]
        
        # Process all chunks concurrently
        completed_results = await asyncio.gather(*tasks)
        found_results = [result for result in completed_results if result is not None]

        if not found_results:
            return "NO_MATCH"

        if is_product_info:
            # Initialize combined results for product information
            combined_results = {
                "name": "NO_MATCH",
                "model_number": "NO_MATCH",
                "serial_number": "NO_MATCH",
                "warranty_info": "NO_MATCH",
                "user_manual": [],
                "other_documents": []
            }

            # Combine all product information results
            for result in found_results:
                for key, value in result.items():
                    if key in ["user_manual", "other_documents"]:
                        if isinstance(value, list):
                            combined_results[key].extend(value)
                        elif value != "NO_MATCH":
                            combined_results[key].append(value)
                    else:
                        if value != "NO_MATCH" and (combined_results[key] == "NO_MATCH" or not combined_results[key]):
                            combined_results[key] = value

            # Remove duplicates while preserving order
            combined_results["user_manual"] = list(dict.fromkeys(combined_results["user_manual"]))
            combined_results["other_documents"] = list(dict.fromkeys(combined_results["other_documents"]))

            return combined_results
        else:
            # For non-product queries, return the most detailed/relevant response
            return max(found_results, key=len) if found_results else "NO_MATCH"

    async def parse_website_async(
            self,
            url: str,
            min_confidence: float = 0.7,
            show_all_images: bool = False,
            parse_description: Optional[str] = None,
            
            model_number: Optional[str] = None,  # Add model_number parameter
            **kwargs
        ) -> ParseResult:
        """Asynchronous version of parse_website"""
        try:
            # Validate and normalize the URL
            if not URLValidator.is_valid_url(url):
                raise ValueError(f"Invalid URL: {url}")
            
            normalized_url = URLValidator.normalize_url(url)
            site_dir = self.site_scraper.create_site_folder(url)
            site_id = os.path.basename(site_dir)
            
            # Scrape website content asynchronously
            unified_scraper = UnifiedScraper()
            html_content = await unified_scraper.scrape_website_async(url)
            if not html_content:
                raise Exception("Failed to scrape website")
            
            # Clean content
            cleaned_content = unified_scraper.clean_content(html_content)
            
            # Extract images
            images = self.site_scraper.extract_images(html_content, url)
            image_urls = [
                URLValidator.resolve_relative_url(normalized_url, img['url']) 
                for img in images
            ]
            
            # Download images asynchronously
            downloaded_images = await self.image_loader.download_images_async(image_urls, normalized_url)
            downloaded_files = [path[1] for path in downloaded_images] if downloaded_images else []
            
            # Store base URL
            self.site_scraper.base_url = url
            
            # Find document links
            document_links = self.find_pdf_links(html_content)
            
            # Analyze content
            content_analysis = self.content_analyzer.analyze_content(cleaned_content)
            
            # Find matching images
            image_matches = self.content_analyzer.find_matching_images(
                content_analysis=content_analysis,
                available_images=image_urls,
                threshold=(0.0 if show_all_images else min_confidence)
            )
            
            # Perform Gemini parsing if description provided
            gemini_result = None
            if parse_description:
                processed_chunks = self.preprocess_content(cleaned_content)
                gemini_result = await self.parse_with_gemini_async(processed_chunks, parse_description)
            
            # Create parse result
            result = ParseResult(
                site_id=site_id,
                content_analysis=content_analysis,
                image_matches=image_matches,
                raw_content=cleaned_content,
                gemini_parse_result=gemini_result,
                downloaded_files=downloaded_files,
                pdf_links=document_links
            )
            
            # Save results
            await self._save_parse_result_async(result)
            
            # Save results using CSVResultManager if available AND model_number is provided
            if self.result_manager and model_number:
                self.result_manager.save_result(
                    url=url,
                    model_number=model_number,
                    parse_result=result
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing website: {str(e)}")
            raise

    async def _save_parse_result_async(self, result: ParseResult):
        """Asynchronously save parse result to file"""
        result_path = os.path.join(self.results_dir, f"{result.site_id}.json")
        async with aiofiles.open(result_path, 'w') as f:
            await f.write(json.dumps(result.__dict__, indent=2))
    
        
    async def download_documents(self, doc_links: List[str], site_id: str) -> Dict[str, List[str]]:
        try:
            doc_dir = os.path.join(self.data_dir, site_id, "documents")
            os.makedirs(doc_dir, exist_ok=True)
            self.doc_downloader.base_url = self.site_scraper.base_url
            self.doc_downloader.download_dir = doc_dir
            
            async with aiohttp.ClientSession() as session:
                downloaded_files = await self.doc_downloader.download_documents_async(
                    doc_links=doc_links,
                    session=session
                )
            return downloaded_files
        except Exception as e:
            logger.error(f"Error downloading documents: {str(e)}")
            return {}

    def preprocess_content(self, html_content: str) -> List[str]:
        """Preprocess HTML content"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for element in soup(['script', 'style']):
            element.decompose()
        
        texts = []
        for element in soup.stripped_strings:
            text = element.strip()
            if text:
                texts.append(text)
        
        return texts

    def find_pdf_links(self, html_content: str) -> List[str]:
        """Find PDF and DOCX links in HTML content"""
        soup = BeautifulSoup(html_content, 'html.parser')
        document_links = []
        
        # Define allowed document extensions
        ALLOWED_EXTENSIONS = ('.pdf', '.docx')
        
        for link in soup.find_all('a'):
            href = link.get('href')
            if href:
                href = href.strip()
                
                # Check if the link ends with allowed extensions
                if href.lower().endswith(ALLOWED_EXTENSIONS):
                    # Make absolute URL if relative
                    if not href.startswith(('http://', 'https://')):
                        try:
                            base_url = urlparse(self.site_scraper.base_url)
                            if href.startswith('/'):
                                href = f"{base_url.scheme}://{base_url.netloc}{href}"
                            else:
                                href = f"{base_url.scheme}://{base_url.netloc}/{base_url.path.rstrip('/')}/{href}"
                        except (AttributeError, ValueError):
                            continue
                    
                    document_links.append(href)
        
        # Remove duplicates while preserving order
        return list(dict.fromkeys(document_links))

    def update_image_verification(self, site_id: str, image_url: str, verified: bool) -> bool:
        """Update user verification for an image match"""
        try:
            result_path = os.path.join(self.results_dir, f"{site_id}.json")
            if not os.path.exists(result_path):
                logger.error(f"No parse result found for site ID: {site_id}")
                return False
            
            with open(result_path, 'r') as f:
                data = json.load(f)
            
            for img_match in data['image_matches']:
                if img_match['url'] == image_url:
                    image_match = ImageMatch(
                        url=img_match['url'],
                        path=img_match['path'],
                        confidence=img_match['confidence'],
                        category=img_match['category'],
                        tags=img_match['tags']
                    )
                    
                    img_match['user_verified'] = verified
                    img_match['verification_timestamp'] = datetime.now().isoformat()
                    
                    self.content_analyzer.update_user_choice(image_match, verified)
                    
                    with open(result_path, 'w') as f:
                        json.dump(data, f, indent=2)
                    
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error updating image verification: {str(e)}")
            return False

    def _save_parse_result(self, result: ParseResult):
        """Save parse result to file"""
        result_path = os.path.join(self.results_dir, f"{result.site_id}.json")
        with open(result_path, 'w') as f:
            json.dump(result.__dict__, f, indent=2)