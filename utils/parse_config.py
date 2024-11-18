from dataclasses import dataclass
import yaml
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

@dataclass
class ParserConfig:
    model_name: str
    data_dir: str
    chunk_size: int
    min_confidence: float
    allowed_extensions: tuple
    max_retries: int
    timeout: int
    api_key: str

class ConfigLoader:
    @staticmethod
    def load_config(config_path: str) -> ParserConfig:
        """Load configuration from a YAML file and .env"""
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # Get the API key from the environment variable
        config_data['api_key'] = os.getenv('API_KEY')
        
        # Return an instance of ParserConfig with loaded data
        return ParserConfig(**config_data)