# LLM-Scraper-main/api/url_processor_api.py
from flask import Flask, request, jsonify
from typing import Optional
import logging
import os
from parse import UnifiedParser
from utils.parse_config import ConfigLoader
from utils.parse_result import ParseResult

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ParserAPI:
    def __init__(self):
        # Initialize configuration
        self.config = ConfigLoader(
            api_key=os.getenv('GEMINI_API_KEY'),
            model_name=os.getenv('MODEL_NAME', 'gemini-pro'),
            data_dir=os.getenv('DATA_DIR', './data')
        )
        # Initialize parser
        self.parser = UnifiedParser(config=self.config)

    def process_url(self, url: str, model_number: Optional[str] = None, 
                   parse_description: Optional[str] = None, 
                   min_confidence: float = 0.7,
                   show_all_images: bool = False) -> ParseResult:
        try:
            result = self.parser.parse_website(
                url=url,
                min_confidence=min_confidence,
                show_all_images=show_all_images,
                parse_description=parse_description,
                model_number=model_number
            )
            return result
        except Exception as e:
            logger.error(f"Error processing URL {url}: {str(e)}")
            raise
        
@app.route('/process_url', methods=['POST'])
def parse_url():
    try:
        # get data from request
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'error': 'No URL provided'}), 400
        
        # extract parameters from request
        url = data['url']
        model_number = data.get('model_number')
        parse_description = data.get('parse_description')
        min_confidence = float(data.get('min_confidence', 0.7))
        show_all_images = bool(data.get('show_all_images', False))
        
        # initialize parser
        parser_api = ParserAPI()
        
        # process URL
        result = parser_api.process_url(
            url=url,
            model_number=model_number,
            parse_description=parse_description,
            min_confidence=min_confidence,
            show_all_images=show_all_images
        )
        
        # Convert result to response format
        response_data = {
            'site_id': result.site_id,
            'content_analysis': result.content_analysis,
            'image_matches': [
                {
                    'url': match.url,
                    'confidence': match.confidence,
                    'context': match.context
                } for match in result.image_matches
            ] if result.image_matches else[],
            'raw_content': result.raw_content,
            'gemini_parse_result': result.gemini_parse_result,
            'downloaded_files': result.downloaded_files,
            'pdf_links': result.pdf_links,
            'status': 'success'
        }
        
        return jsonify(response_data), 200
    except ValueError as ve:
        logger.error(f"ValueError: {str(ve)}")
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Error processing URL: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500
    
@app.route('/batch-parse', methods=['POST'])
def batch_parse():
    try:
        data = request.json
        if not data or 'urls' not in data:
            return jsonify({'error': 'No URLs provided'}), 400
        
        urls = data['urls']
        model_number = data.get('model_number')
        
        parser_api = ParserAPI()
        results = []
        
        for url in urls:
            try:
                result = parser_api.process_url(url, model_number=model_number)
                results.append({
                    'url': url,
                    'status': 'success',
                    'result': {
                        'site_id': result.site_id,
                        'content_analysis': result.content_analysis,
                        'image_matches': [
                            {
                                'url': match.url,
                                'confidence': match.confidence,
                                'context': match.context
                            } for match in result.image_matches
                        ] if result.image_matches else [],
                        # 'raw_content': result.raw_content,
                        # 'gemini_parse_result': result.gemini_parse_result,
                        'downloaded_files': result.downloaded_files,
                        'pdf_links': result.pdf_links
                    }
                })
            except Exception as e:
                results.append({
                    'url': url,
                    'status': 'error',
                    'error': str(e)
                })
        return jsonify({'status': 'success', 'results': results})
    
    except Exception as e:
        logger.error(f"Error in batch parse: {str(e)}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    # Load env variables
    from dotenv import load_dotenv
    load_dotenv()
    
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    app.run(host='0.0.0.0', port=port, debug=debug)
    
# gunicorn -w 4 -b 0.0.0.0:5000 parser_api:app
