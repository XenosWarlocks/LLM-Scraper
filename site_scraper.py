# used in parse.py
# site_scraper.py
import aiohttp
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
import logging
from urllib.parse import urlparse, urljoin
import os
import hashlib

class SiteScraper:
    def __init__(self, download_dir: str = "data"):
        """Initialize the site scraper"""
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)

    def create_site_folder(self, url: str) -> str:
        """Create a folder name from URL"""
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.replace('www.', '').split('.')[0]
        folder_name = hashlib.md5(domain.encode()).hexdigest()[:8]
        site_dir = os.path.join(self.download_dir, folder_name)
        os.makedirs(site_dir, exist_ok=True)
        return site_dir

    def scrape_page(self, url: str) -> Optional[str]:
        """Scrape webpage content"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logging.error(f"Error scraping page: {str(e)}")
            return None

    def extract_images(self, html_content: str, base_url: str) -> List[Dict]:
        """Extract image information from HTML"""
        soup = BeautifulSoup(html_content, 'html.parser')
        images = []

        for img in soup.find_all('img'):
            src = img.get('src')
            if src:
                # Handle relative URLs
                if not src.startswith(('http://', 'https://')):
                    src = urljoin(base_url, src)

                images.append({
                    'url': src,
                    'alt': img.get('alt', ''),
                    'title': img.get('title', ''),
                    'dimensions': {
                        'width': img.get('width', ''),
                        'height': img.get('height', '')
                    }
                })

        return images

    def clean_content(self, html_content: str) -> str:
        """Clean and extract meaningful content from HTML"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for element in soup(['script', 'style', 'iframe', 'noscript']):
            element.decompose()
        
        # Extract text content
        text = soup.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text
    
    # async def scrape_page_async(self, url: str, session: aiohttp.ClientSession) -> str:
    #     """Scrape webpage asynchronously"""
    #     try:
    #         async with session.get(url) as response:
    #             return await response.text()
    #     except Exception as e:
    #         logging.error(f"Error scraping {url}: {str(e)}")
    #         return None