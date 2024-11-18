# result_manager.py
import json
import os
import csv
from typing import List, Dict, Union, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime

from utils.prod_info import ProductInfo

from utils.parse_result import ParseResult

class CSVResultManager:
    def __init__(self, base_dir: str):
        """
        Initialize the CSV Result Manager
        
        Args:
            base_dir (str): Base directory for storing results (e.g., "data")
        """
        self.base_dir = base_dir
        
    def _get_model_dir(self, model_number: str) -> str:
        """Create and return model-specific directory path"""
        if not model_number:
            model_dir = os.path.join(self.base_dir, "default")
        else:
            model_dir = os.path.join(self.base_dir, model_number)
        
        os.makedirs(model_dir, exist_ok=True)
        return model_dir

    def _get_csv_filepath(self, model_number: str) -> str:
        """Get the CSV file path for the given model number"""
        model_dir = self._get_model_dir(model_number)
        return os.path.join(model_dir, "results.csv")

    def _process_gemini_result(self, gemini_result: Union[Dict, str], url: str, site_id: str) -> ProductInfo:
        if isinstance(gemini_result, dict):
            # Extract product information details
            product_name = gemini_result.get('product_name', 'NO_MATCH')
            model_number = gemini_result.get('model_number', 'NO_MATCH')
            serial_number = gemini_result.get('serial_number', 'NO_MATCH')
            warranty_info = gemini_result.get('warranty_info', 'NO_MATCH')
            user_manual = '|'.join(gemini_result.get('user_manual', []))
            other_documents = '|'.join(gemini_result.get('other_documents', []))
            additional_info = '|'.join(gemini_result.get('additional_info', []))

            return ProductInfo(
                product_name=product_name,
                model_number=model_number,
                serial_number=serial_number,
                warranty_info=warranty_info,
                user_manual=user_manual,
                other_documents=other_documents,
                additional_info=additional_info,
                url=url,
                site_id=site_id,
                timestamp=datetime.now().isoformat()
            )
        else:
            # Handle string results (non-product queries)
            return ProductInfo(
                additional_info=[str(gemini_result)],
                url=url,
                site_id=site_id
            )

    def save_result(self, parse_result: 'ParseResult', model_number: str, url: str):
        """
        Save parse result to CSV file
        
        Args:
            parse_result: The parsing result object
            model_number: Product model number for directory organization
            url: Original URL that was parsed
        """
        try:
            # Process the Gemini result
            product_info = self._process_gemini_result(
                parse_result.gemini_parse_result,
                url,
                parse_result.site_id
            )

            # Get CSV filepath
            filepath = self._get_csv_filepath(model_number)

            # Determine if we need to write headers
            file_exists = os.path.exists(filepath)

            mode = 'a' if file_exists else 'w'
            with open(filepath, mode, newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=asdict(product_info).keys())

                # Write headers if new file
                if not file_exists:
                    writer.writeheader()

                writer.writerow(asdict(product_info))

            # Save raw content, image matches, and PDF links
            self._save_additional_data(parse_result, model_number)

        except Exception as e:
            print(f"Error saving to CSV: {e}")
            raise

    def _save_additional_data(self, parse_result: 'ParseResult', model_number: str):
        """Save additional data like raw content and image matches"""
        model_dir = self._get_model_dir(model_number)
        
        # Save raw content
        raw_content_path = os.path.join(model_dir, f"{parse_result.site_id}_raw.txt")
        with open(raw_content_path, 'w', encoding='utf-8') as f:
            f.write(parse_result.raw_content)
        
        # Save image matches
        if parse_result.image_matches:
            image_matches_path = os.path.join(model_dir, f"{parse_result.site_id}_images.json")
            with open(image_matches_path, 'w') as f:
                json.dump(parse_result.image_matches, f, indent=2)
        
        # Save PDF links
        if parse_result.pdf_links:
            pdf_links_path = os.path.join(model_dir, f"{parse_result.site_id}_pdfs.txt")
            with open(pdf_links_path, 'w') as f:
                f.write('\n'.join(parse_result.pdf_links))

    def read_results(self, model_number: str) -> List[Dict]:
        """Read all results for a given model number"""
        filepath = self._get_csv_filepath(model_number)
        
        if not os.path.exists(filepath):
            return []
            
        results = []
        with open(filepath, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Convert pipe-separated strings back to lists
                for field in ['user_manual', 'other_documents', 'additional_info']:
                    if row[field]:
                        row[field] = row[field].split('|')
                    else:
                        row[field] = []
                results.append(row)
                
        return results

    def get_model_results_summary(self, model_number: str) -> Dict:
        """Get a summary of results for a model number"""
        results = self.read_results(model_number)
        
        return {
            'total_sites': len(results),
            'sites_with_manuals': len([r for r in results if r['user_manual']]),
            'sites_with_warranty': len([r for r in results if r['warranty_info'] != 'NO_MATCH']),
            'total_documents': sum(len(r['user_manual']) + len(r['other_documents']) for r in results),
            'latest_update': max((r['timestamp'] for r in results), default=None) if results else None
        }