# download_manager.py
from typing import Dict, Optional, Tuple
from datetime import datetime
import json
import hashlib
from pathlib import Path

from loader import ImageLoader
from result_manager import CSVResultManager
from utils.parse_result import ParseResult

class DownloadManager:
    def __init__(self, base_dir: str = "data"):
        """
        Initialize the Download Manager with ImageLoader and CSVResultManager
        
        Args:
            base_dir (str): Base directory for storing all data
        """
        Path(base_dir).mkdir(parents=True, exist_ok=True)
        self.base_dir = base_dir
        
    def process_parse_result(
        self, 
        parsed_result: Dict, 
        model_number: str,
        url: str,
        raw_content: str,
        site_id: str,
        image_matches: list,
        pdf_links: list,
        html_content: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Process parsing results, save data, and prepare download files
        
        Args:
            parsed_result: The parsed result dictionary from Gemini
            model_number: Product model number
            url: Source URL
            raw_content: Raw text content
            site_id: Existing site ID from session state
            image_matches: List of image matches from session state
            pdf_links: List of PDF links from session state
            html_content: Optional HTML content for image processing
            
        Returns:
            Tuple[str, str]: Paths to the generated CSV and JSON files
        """
        # Create model-specific directory
        model_dir = Path(self.base_dir) / (model_number or "default")
        model_dir.mkdir(exist_ok=True)
        
        # Create ParseResult object using existing session state data
        parse_result = ParseResult(
            site_id=site_id,
            gemini_parse_result=parsed_result,
            raw_content=raw_content,
            image_matches=image_matches,
            pdf_links=pdf_links,
            content_analysis=""  # Placeholder for content analysis
        )
        
        # Initialize CSVResultManager for this model
        csv_manager = CSVResultManager(str(model_dir))
        
        # Save results using CSVResultManager
        csv_manager.save_result(parse_result, model_number, url)
        
        # Get CSV file path
        csv_path = csv_manager._get_csv_filepath(model_number)
        
        # Create JSON file path and save JSON version
        json_path = model_dir / f"{site_id}_result.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                'parse_result': parsed_result,
                'metadata': {
                    'url': url,
                    'site_id': site_id,
                    'model_number': model_number,
                    'timestamp': datetime.now().isoformat(),
                    'image_matches': [
                        {'url': img.url, 'confidence': img.confidence} 
                        for img in image_matches
                    ] if image_matches else [],
                    'pdf_links': pdf_links
                }
            }, f, indent=2)
        
        return str(csv_path), str(json_path)

    def get_download_data(self, file_path: str) -> bytes:
        """
        Read file content for download
        
        Args:
            file_path: Path to the file to be downloaded
            
        Returns:
            bytes: File content as bytes
        """
        with open(file_path, 'rb') as f:
            return f.read()