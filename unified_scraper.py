
# unified_scraper.py
from abc import ABC, abstractmethod
from typing import Optional, List, Dict
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import hashlib
import os
import time
import logging
import aiohttp
import asyncio
from pathlib import Path
from doc_downloader import DocumentDownloader

logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    """Abstract base class for scrapers"""

    @abstractmethod
    def scrape_page(self, url: str) -> Optional[str]:
        pass

    def clean_content(self, html_content: str) -> str:
        """Clean and extract meaningful content from HTML"""
        soup = BeautifulSoup(html_content, 'html.parser')
        for element in soup(['script', 'style', 'iframe', 'noscript']):
            element.decompose()
        text = soup.get_text(separator=' ', strip=True)
        return ' '.join(text.split())

class StaticScraper(BaseScraper):
    """For static content using requests"""

    def __init__(self):
        self.session = requests.Session()
        self.base_url = ""

    def scrape_page(self, url: str) -> Optional[str]:
        try:
            self.base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Static scraping failed: {e}")
            return None

class DynamicScraper(BaseScraper):
    """For dynamic content using Selenium"""

    def __init__(self):
        self.driver = None
        self.base_url = ""

    def setup_driver(self):
        options = Options()
        options.add_argument("--headless")
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(90)

    def scrape_page(self, url: str) -> Optional[str]:
        try:
            self.base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            if not self.driver:
                self.setup_driver()
            self.driver.get(url)
            time.sleep(3)  # Allow time for dynamic content to load
            return self.driver.page_source
        except Exception as e:
            logger.error(f"Dynamic scraping failed: {e}")
            return None
        finally:
            if self.driver:
                self.driver.quit()

class UnifiedScraper:
    """Factory class to choose appropriate scraper"""

    def __init__(self, download_dir: str = "downloads"):
        self.static_scraper = StaticScraper()
        self.dynamic_scraper = DynamicScraper()
        self.doc_downloader = DocumentDownloader(base_url="", download_dir=download_dir)
        self.base_url = ""

    def _needs_dynamic_scraping(self, url: str) -> bool:
        """Detects if a page requires dynamic scraping"""
        dynamic_patterns = ['angular.io', 'react.', '#!', 'vue.']
        return any(pattern in url for pattern in dynamic_patterns)

    def scrape(self, url: str) -> Optional[str]:
        """Scrape and clean content from a URL using the appropriate scraper"""
        self.base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        scraper = self.dynamic_scraper if self._needs_dynamic_scraping(url) else self.static_scraper
        raw_content = scraper.scrape_page(url)
        if raw_content:
            return scraper.clean_content(raw_content)
        return None

    def find_document_links(self, html_content: str) -> List[str]:
        """Extract document links (PDF, DOC, etc.) from HTML content"""
        soup = BeautifulSoup(html_content, 'html.parser')
        doc_extensions = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx')
        doc_links = []
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            if any(href.lower().endswith(ext) for ext in doc_extensions):
                doc_links.append(href)
                
        return doc_links

    async def download_documents(
        self,
        doc_links: List[str],
        site_id: str
    ) -> Dict[str, List[str]]:
        """Download documents for a specific site"""
        try:
            # Create site-specific document directory
            doc_dir = os.path.join(self.doc_downloader.download_dir, site_id, "documents")
            os.makedirs(doc_dir, exist_ok=True)
            
            # Update doc_downloader configuration
            self.doc_downloader.base_url = self.base_url
            self.doc_downloader.download_dir = doc_dir
            
            async with aiohttp.ClientSession() as session:
                return await self.doc_downloader.download_documents_async(
                    doc_links=doc_links,
                    session=session
                )
        except Exception as e:
            logger.error(f"Error downloading documents: {str(e)}")
            return {"downloaded": [], "failed": doc_links}

    def create_site_folder(self, url: str) -> str:
        """Create a folder name from URL"""
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.replace('www.', '').split('.')[0]
        folder_name = hashlib.md5(domain.encode()).hexdigest()[:8]
        site_dir = os.path.join(self.doc_downloader.download_dir, folder_name)
        os.makedirs(site_dir, exist_ok=True)
        return site_dir

    def scrape_website(self, url: str) -> Optional[str]:
        """Scrape content from the given URL."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logging.error(f"Error scraping website: {str(e)}")
            return None

    def clean_content(self, html_content: str) -> str:
        """Clean HTML content."""
        soup = BeautifulSoup(html_content, 'html.parser')
        for element in soup(['script', 'style', 'iframe', 'noscript']):
            element.decompose()
        text = soup.get_text(separator=' ', strip=True)
        return ' '.join(text.split())