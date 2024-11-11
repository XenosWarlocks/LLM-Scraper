# parse.py
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
import requests
from bs4 import BeautifulSoup
from typing import Optional, Union, List
import logging
import os
import hashlib
from urllib.parse import urlparse
import mimetypes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

template = (
    "You are tasked with extracting specific information from the following text content: {dom_content}. "
    "Please follow these instructions carefully: \n\n"
    "1. **Extract Information:** Only extract the information that directly matches the provided description: {parse_description}. "
    "2. **No Extra Content:** Do not include any additional text, comments, or explanations in your response. "
    "3. **Empty Response:** If no information matches the description, return an empty string ('')."
    "4. **Direct Data Only:** Your output should contain only the data that is explicitly requested, with no other text."
)

model = OllamaLLM(model="llama3")

class OlamaParser:
    def __init__(self, model_name: str, download_dir: str = "downloads"):
        """
        Initialize the OllamaParser with model configuration and download directory.
        
        Args:
            model_name: Name of the Ollama model to use
            download_dir: Directory to store downloaded files
        """
        self.model = OllamaLLM(model="llama3")
        self.prompt = ChatPromptTemplate.from_template(template)
        self.download_dir = download_dir
        
        # Create download directory if it doesn't exist
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

    def download_file(self, url: str, filename: Optional[str] = None) -> str:
        """
        Download a file from a URL and save it to the download directory.
        
        Args:
            url: URL of the file to download
            filename: Optional custom filename, if not provided will be derived from URL
            
        Returns:
            str: Path to the downloaded file
        """
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()

            # Generate filename if not provided
            if not filename:
                # Try to get filename from URL
                parsed_url = urlparse(url)
                filename = os.path.basename(parsed_url.path)

                # If no filename in URL, create one based on content type
                if not filename:
                    content_type = response.headers.get('content-type')
                    ext = mimetypes.guess_extension(content_type) or ''
                    filename = f"{hashlib.md5(url.encode()).hexdigest()}{ext}"
            
            file_path = os.path.join(self.download_dir, filename)

            # Download the file in chunks
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            logger.info(f"Successfully downloaded file to: {file_path}")
            return file_path
        
        except requests.RequestException as e:
            logger.error(f"Error downloading file from {url}: {str(e)}")
            raise
    
    def parse_with_ollama(self, dom_chunks: List[str], parse_description: str) -> str:
        """
        Parse content chunks using the Ollama model.
        
        Args:
            dom_chunks: List of content chunks to parse
            parse_description: Description of what to extract
            
        Returns:
            str: Concatenated parsing results
        """
        chain = self.prompt | self.model
        parsed_results = []

        total_chunks = len(dom_chunks)
    
        for i, chunk in enumerate(dom_chunks, start=1):
            try:
                response = chain.invoke(
                    {"dom_content": chunk, "parse_description": parse_description}
                )
                logger.info(f"Parsed batch: {i} of {total_chunks}")
                parsed_results.append(response)
            
            except Exception as e:
                logger.error(f"Error parsing chunk {i} of {total_chunks}: {str(e)}")
                raise

        return "\n".join(parsed_results)
    
    def download_images_from_html(self, html_content: str) -> List[str]:
        """
        Extract and download all images from HTML content.
        
        Args:
            html_content: HTML content containing image tags
            
        Returns:
            List[str]: List of paths to downloaded images
        """

        soup = BeautifulSoup(html_content, 'html.parser')
        image_paths = []

        for img in soup.find_all('img'):
            src = img.get('src')
            if src and (src.startswith('http://') or src.startswith('https://')):
                try:
                    image_path = self.download_file(src)
                    image_paths.append(image_path)
                except Exception as e:
                    logger.error(f"Error downloading image from {src}: {str(e)}")
                    continue
        
        return image_paths
