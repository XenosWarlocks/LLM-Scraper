# loader.py
import os
import hashlib
import requests
from urllib.parse import urlparse
import mimetypes
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageLoader:
    def __init__(self, base_dir: str = "data"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
    def _create_site_hash(self, url: str) -> str:
        domain = urlparse(url).netloc
        return hashlib.md5(domain.encode()).hexdigest()[:8]
    
    def _get_file_extension(self, url: str, content_type: Optional[str] = None) -> str:
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        if ext and ext in ['.jpg', '.jpeg', '.png', '.webp', '.svg']:
            return ext
        if content_type:
            guessed_ext = mimetypes.guess_extension(content_type)
            if guessed_ext:
                return guessed_ext
        return '.jpg'
    
    def _create_image_filename(self, url: str, content_type: Optional[str] = None) -> str:
        name_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        ext = self._get_file_extension(url, content_type)
        return f"img_{name_hash}{ext}"
    
    def download_image(self, url: str, site_url: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            # Create site-specific directory
            site_hash = self._create_site_hash(site_url)
            site_dir = self.base_dir / site_hash
            site_dir.mkdir(exist_ok=True)
            
            # Download image
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Create filename and paths
            filename = self._create_image_filename(url, response.headers.get('content-type'))
            rel_path = f"{site_hash}/{filename}"
            abs_path = site_dir / filename
            
            # Save image
            with open(abs_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"Successfully downloaded image: {rel_path}")
            return rel_path, str(abs_path)
            
        except Exception as e:
            logger.error(f"Error downloading image from {url}: {str(e)}")
            return None, None
    
    def download_images_from_html(self, html_content: str, site_url: str) -> List[Tuple[str, str]]:
        soup = BeautifulSoup(html_content, 'html.parser')
        downloaded_images = []
        
        # Process all img tags
        for img in soup.find_all('img'):
            src = img.get('src')
            if not src:
                continue
                
            # Handle relative URLs
            if not src.startswith(('http://', 'https://')):
                base_url = f"{urlparse(site_url).scheme}://{urlparse(site_url).netloc}"
                if src.startswith('/'):
                    src = f"{base_url}{src}"
                else:
                    src = f"{base_url}/{src}"
            
            # Download image
            paths = self.download_image(src, site_url)
            if paths[0] and paths[1]:  # Only add successful downloads
                downloaded_images.append(paths)
        
        return downloaded_images
    
    def get_site_images(self, site_hash: str) -> List[str]:
        site_dir = self.base_dir / site_hash
        if not site_dir.exists():
            return []
            
        return [f.name for f in site_dir.glob('img_*')]
    
    def cleanup_old_images(self, max_age_days: int = 30):
        import time
        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60
        
        for site_dir in self.base_dir.iterdir():
            if site_dir.is_dir():
                for image_file in site_dir.glob('img_*'):
                    if current_time - image_file.stat().st_mtime > max_age_seconds:
                        image_file.unlink()
                        logger.info(f"Deleted old image: {image_file}")
                
                # Remove empty directories
                if not any(site_dir.iterdir()):
                    site_dir.rmdir()
                    logger.info(f"Removed empty directory: {site_dir}")
                    