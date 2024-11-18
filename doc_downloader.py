import asyncio
from collections import defaultdict
import os
from typing import Dict, List, Optional
from urllib.parse import urljoin
import uuid
import aiohttp
import logging

class DocumentDownloader:
    def __init__(self, base_url: str, download_dir: str):
        self.base_url = base_url
        self.download_dir = download_dir

    async def download_file_async(
        self, 
        url: str, 
        session: aiohttp.ClientSession,
        chunk_size: int = 8192
    ) -> Optional[str]:
        """Download a single file asynchronously"""
        try:
            # Handle relative URLs
            if not url.startswith(('http://', 'https://')):
                url = urljoin(self.base_url, url)
                
            # Create filename from URL
            filename = url.split('/')[-1]
            filepath = os.path.join(self.download_dir, filename)
            
            async with session.get(url) as response:
                if response.status == 200:
                    with open(filepath, 'wb') as f:
                        while True:
                            chunk = await response.content.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                    return filepath
                return None
        except Exception as e:
            logging.error(f"Error downloading file {url}: {str(e)}")
            return None

    async def download_documents_async(
        self,
        doc_links: List[str],
        session: aiohttp.ClientSession
    ) -> Dict[str, List[str]]:
        """Download multiple documents asynchronously"""
        downloaded_files = defaultdict(list)

        tasks = [
            self.download_file_async(link, session)
            for link in doc_links
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result, link in zip(results, doc_links):
            if isinstance(result, str):  # Successful download returns filepath
                ext = os.path.splitext(link)[1].lower()
                downloaded_files[ext].append(result)
            else:
                logging.error(f"Error downloading file {link}: {str(result)}")

        return dict(downloaded_files)