from langchain_google_genai import ChatGoogleGenerativeAI
import google.generativeai as genai
from langchain_core.prompts import ChatPromptTemplate
import requests
from bs4 import BeautifulSoup
from typing import Optional, Union, List
import logging
import os
import hashlib
from urllib.parse import urlparse
import mimetypes
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class GeminiParser:
    def __init__(self, api_key: str, model_name: str = "gemini-pro", download_dir: str = "downloads"):
        """
        Initialize the GeminiParser with model configuration and download directory.
        
        Args:
            api_key: Google API key for Gemini
            model_name: Name of the Gemini model to use
            download_dir: Directory to store downloaded files
        """
        # Configure Gemini
        genai.configure(api_key=api_key)
        self.model = ChatGoogleGenerativeAI(model=model_name)
        self.download_dir = download_dir
        
        # Create download directory if it doesn't exist
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
        
        # Improved prompt template with clear instructions and examples
        self.prompt = ChatPromptTemplate.from_template(
            "You are a precise information extractor. Analyze the following content and extract "
            # "ONLY the specific information requested. If the information is not present, return "
            "EXACTLY the string 'NO_MATCH'.\n\n"
            "Content to analyze: {dom_content}\n\n"
            "Information to extract: {parse_description}\n\n"
            "Rules:\n"
            "1. Extract ONLY the exact information requested\n"
            "2. If information is not found, return 'NO_MATCH'\n"
            "3. Do not include any explanations or additional text\n"
            "4. Do not make assumptions or inferences\n\n"
            "Example inputs and outputs:\n"
            "- Query: 'what is the model number?'\n"
            "- Query: 'what is the product title and model?'\n"
            "- Query: 'what is the price?'\n"
            "  Output: 'NO_MATCH'\n\n"
            "Now, provide your response following these rules:"
        )

    def preprocess_content(self, html_content: str) -> List[str]:
        """
        Preprocess HTML content to improve parsing accuracy.
        
        Args:
            html_content: Raw HTML content to process
            
        Returns:
            List of processed text chunks
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for element in soup(['script', 'style']):
            element.decompose()
        
        # Extract text from specific meaningful elements
        meaningful_elements = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                                          'p', 'div', 'span', 'title'])
        
        # Process each element's text
        processed_chunks = []
        for element in meaningful_elements:
            text = element.get_text(strip=True)
            if text:
                processed_chunks.append(text)
        
        return processed_chunks

    def parse_with_gemini(self, dom_chunks: List[str], parse_description: str) -> str:
        """
        Parse content chunks using the Gemini model with improved result handling.
        
        Args:
            dom_chunks: List of content chunks to parse
            parse_description: Description of what to extract
            
        Returns:
            Parsed results or 'NO_MATCH' if nothing found
        """
        chain = self.prompt | self.model
        parsed_results = []
        
        total_chunks = len(dom_chunks)
        
        for i, chunk in enumerate(dom_chunks, start=1):
            try:
                response = chain.invoke({
                    "dom_content": chunk,
                    "parse_description": parse_description
                })
                
                # Extract content and clean it
                content = response.content if hasattr(response, 'content') else str(response)
                content = content.strip()
                
                # Only add non-empty and non-NO_MATCH results
                if content and content != 'NO_MATCH':
                    parsed_results.append(content)
                
                logger.info(f"Parsed chunk {i} of {total_chunks}: "
                          f"{'Found match' if content != 'NO_MATCH' else 'No match'}")
                
            except Exception as e:
                logger.error(f"Error parsing chunk {i} of {total_chunks}: {str(e)}")
                continue
        
        # Return combined results or NO_MATCH if nothing found
        if parsed_results:
            # Remove duplicates while preserving order
            unique_results = list(dict.fromkeys(parsed_results))
            return "\n".join(unique_results)
        return "NO_MATCH"

    def download_file(self, url: str, filename: Optional[str] = None) -> str:
        """
        Download a file from a URL and save it to the download directory.
        
        Args:
            url: URL of the file to download
            filename: Optional custom filename
            
        Returns:
            Path to the downloaded file
        """
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()

            if not filename:
                parsed_url = urlparse(url)
                filename = os.path.basename(parsed_url.path)
                if not filename:
                    content_type = response.headers.get('content-type')
                    ext = mimetypes.guess_extension(content_type) or ''
                    filename = f"{hashlib.md5(url.encode()).hexdigest()}{ext}"
            
            file_path = os.path.join(self.download_dir, filename)

            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            logger.info(f"Successfully downloaded file to: {file_path}")
            return file_path
        
        except requests.RequestException as e:
            logger.error(f"Error downloading file from {url}: {str(e)}")
            raise

    def download_images_from_html(self, html_content: str) -> List[str]:
        """
        Extract and download all images from HTML content.
        
        Args:
            html_content: HTML content containing image tags
            
        Returns:
            List of paths to downloaded images
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

    def find_pdf_links(self, html_content: str) -> List[str]:
        """
        Find all PDF links in the HTML content.
        
        Args:
            html_content: HTML content to search for PDF links
            
        Returns:
            List of PDF URLs found in the content
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        pdf_links = []

        for link in soup.find_all('a'):
            href = link.get('href')
            if href and href.lower().endswith('.pdf'):
                if not href.startswith(('http://', 'https://')):
                    continue
                pdf_links.append(href)

        return pdf_links