import re
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Set, Optional
import mimetypes
import os
import logging
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup, Tag

@dataclass
class DocumentLink:
    url: str
    title: str
    file_type: str
    category: str
    size: Optional[int] = None

class DocumentDownloader:
    """Handles downloading and processing of documentation files."""
    DOCUMENT_KEYWORDS = {
        'manual': [
            r'manual', r'guide', r'handbook', r'instructions?',
            r'specifications?', r'specs?', r'documentation',
            r'user\s*guide', r'owner\'?s?\s*manual', r'quick\s*start',
            r'installation\s*guide', r'setup\s*guide', r'reference',
            r'technical\s*doc'
        ],
        'specification': [
            r'specifications?', r'specs?', r'technical\s*specs?',
            r'product\s*specs?', r'data\s*sheet'
        ],
        'installation': [
            r'installation', r'setup', r'configure', r'assembly',
            r'mounting', r'install\s*guide'
        ]
    }

    ALLOWED_EXTENSIONS = {
        '.pdf', '.doc', '.docx',
        # '.xls', '.xlsx', '.zip', '.rar', '.7z', '.rtf', '.csv', '.txt',
    }

    def __init__(self, base_url: str, download_dir: str):
        self.base_url = base_url
        self.download_dir = download_dir
        self.downloaded_files: Set[str] = set()
        self.session = requests.Session()
        
        # Configure logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Ensure download directory exists
        os.makedirs(download_dir, exist_ok=True)
        
        # Create category subdirectories
        for category in self.DOCUMENT_KEYWORDS.keys():
            os.makedirs(os.path.join(download_dir, category), exist_ok=True)

    def _is_valid_file_type(self, url: str) -> bool:
        """Check if the URL points to an allowed file type."""
        parsed = urlparse(url)
        ext = os.path.splitext(parsed.path)[1].lower()
        return ext in self.ALLOWED_EXTENSIONS
    
    def _categorize_link(self, text: str) -> Optional[str]:
        """Categorize link based on its text content."""
        text = text.lower()
        for category, patterns in self.DOCUMENT_KEYWORDS.items():
            if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
                return category
        return None
    
    def _clean_filename(self, filename: str) -> str:
        """Clean and normalize filename."""
        # Remove invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Replace spaces with underscores
        filename = re.sub(r'\s+', '_', filename)
        return filename.lower()
    
    def _get_file_info(self, url: str) -> Optional[Dict]:
        """Get file information including size and type."""
        try:
            response = self.session.head(url, allow_redirects=True)
            if response.ok:
                content_type = response.headers.get('content-type', '')
                content_length = response.headers.get('content-length')
                return {
                    'type': content_type,
                    'size': int(content_length) if content_length else None
                }
        except Exception as e:
            self.logger.error(f"Error getting file info for {url}: {str(e)}")
        return None
    
    def _download_file(self, doc_link: DocumentLink) -> Optional[str]:
        """Download a single file."""
        try:
            # Create category subfolder path
            category_dir = os.path.join(self.download_dir, doc_link.category)
            
            # Generate unique filename
            base_filename = self._clean_filename(doc_link.title)
            ext = os.path.splitext(urlparse(doc_link.url).path)[1].lower()
            if not ext:
                ext = mimetypes.guess_extension(doc_link.file_type) or '.pdf'
            
            filename = f"{base_filename}{ext}"
            filepath = os.path.join(category_dir, filename)
            
            # Check if file already exists
            if filepath in self.downloaded_files:
                return filepath
            
            # Download file
            response = self.session.get(doc_link.url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            self.downloaded_files.add(filepath)
            self.logger.info(f"Successfully downloaded: {filename}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Error downloading {doc_link.url}: {str(e)}")
            return None
        
    def find_document_links(self, html_content: str) -> List[DocumentLink]:
        """Find and process all document links in the HTML content."""
        soup = BeautifulSoup(html_content, 'html.parser')
        document_links = []
        
        for link in soup.find_all('a', href=True):
            url = urljoin(self.base_url, link.get('href'))
            
            # Skip if not a valid file type
            if not self._is_valid_file_type(url):
                continue
            
            # Get link text and title
            text = link.get_text(strip=True)
            title = link.get('title', text)
            
            # Categorize the link
            category = self._categorize_link(text)
            if not category:
                continue
            
            # Get file information
            file_info = self._get_file_info(url)
            if file_info:
                document_links.append(DocumentLink(
                    url=url,
                    title=title,
                    file_type=file_info['type'],
                    category=category,
                    size=file_info['size']
                ))
        
        return document_links
    
    def download_documents(self, document_links: List[DocumentLink]) -> Dict[str, List[str]]:
        """Download all documents in parallel."""
        downloaded_files = {category: [] for category in self.DOCUMENT_KEYWORDS.keys()}
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_link = {
                executor.submit(self._download_file, link): link 
                for link in document_links
            }
            
            for future in future_to_link:
                link = future_to_link[future]
                try:
                    filepath = future.result()
                    if filepath:
                        downloaded_files[link.category].append(filepath)
                except Exception as e:
                    self.logger.error(f"Error downloading {link.url}: {str(e)}")
        
        return downloaded_files
