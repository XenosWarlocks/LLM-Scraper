import os
from typing import List, Dict, Optional
import json
from datetime import datetime
from dataclasses import dataclass
import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
import numpy as np
from PIL import Image
import hashlib
from urllib.parse import urlparse
import logging
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

vision_api = os.getenv("GOOGLE_VISION_API_KEY")

@dataclass
class ImageMatch:
    url: str
    path: str
    confidence: float
    category: str
    tags: List[str]
    user_verified: bool = False
    timestamp: str = datetime.now().isoformat()

class ContentAnalyzer:
    def __init__(self, api_key: str, model_name: str = "gemini-pro", data_dir: str = "data"):
        """Initialize the content analyzer with AI models and data storage"""
        self.api_key = api_key
        genai.configure(api_key=api_key)
        self.model = ChatGoogleGenerativeAI(model=model_name)
        self.data_dir = data_dir
        self.image_database_path = os.path.join(data_dir, "image_database.json")
        self.learning_data_path = os.path.join(data_dir, "learning_data.json")
        
        # Initialize storage
        self._init_storage()
        
        # Content understanding prompt - Fixed by escaping curly braces
        self.content_prompt = ChatPromptTemplate.from_template("""
            Analyze the following webpage content and extract key information:
            Content: {content}
            
            Please identify:
            1. Main topic/product category
            2. Specific product details (if any)
            3. Key features or specifications
            4. Related categories or products
            5. Important contextual information
            
            Format the response as JSON with these exact keys:
            {{
                "main_category": "",
                "specific_product": "",
                "features": [],
                "related_categories": [],
                "context": ""
            }}
        """)
        
        # Image matching prompt - Fixed by escaping curly braces
        self.image_prompt = ChatPromptTemplate.from_template("""
            Given an image and the following context, determine if this image is relevant:
            Context: {context}
            Image description: {image_description}
            
            Rate the relevance from 0.0 to 1.0 and explain why.
            Format response as JSON:
            {{
                "relevance_score": 0.0,
                "reasoning": "",
                "suggested_tags": []
            }}
        """)

    def _init_storage(self):
        """Initialize storage directories and files"""
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Initialize image database if it doesn't exist
        if not os.path.exists(self.image_database_path):
            self._save_image_database({})
            
        # Initialize learning data if it doesn't exist
        if not os.path.exists(self.learning_data_path):
            self._save_learning_data({
                "category_patterns": {},
                "image_patterns": {},
                "user_preferences": {}
            })

    def _save_image_database(self, data: Dict):
        """Save image database to file"""
        with open(self.image_database_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _save_learning_data(self, data: Dict):
        """Save learning data to file"""
        with open(self.learning_data_path, 'w') as f:
            json.dump(data, f, indent=2)

    def analyze_content(self, content: str) -> Dict:
        """Analyze webpage content to understand context and categories"""
        try:
            chain = self.content_prompt | self.model
            response = chain.invoke({"content": content})
            return json.loads(response.content)
        except Exception as e:
            logging.error(f"Error analyzing content: {str(e)}")
            return {}

    def find_matching_images(self, content_analysis: Dict, available_images: List[str],
                           threshold: float = 0.7) -> List[ImageMatch]:
        """Find images that match the content context"""
        matches = []
        
        # Load learning data
        with open(self.learning_data_path, 'r') as f:
            learning_data = json.load(f)
        
        # Get category patterns
        category = content_analysis.get('main_category', '').lower()
        category_patterns = learning_data['category_patterns'].get(category, {})
        
        for image_path in available_images:
            try:
                # Generate image description (you'll need to implement this)
                image_description = self._generate_image_description(image_path)
                
                # Check against learned patterns
                if self._matches_learned_patterns(image_description, category_patterns):
                    confidence = 0.9  # High confidence for learned patterns
                else:
                    # Use AI to evaluate match
                    chain = self.image_prompt | self.model
                    response = chain.invoke({
                        "context": json.dumps(content_analysis),
                        "image_description": image_description
                    })
                    result = json.loads(response.content)
                    confidence = float(result['relevance_score'])
                
                if confidence >= threshold:
                    matches.append(ImageMatch(
                        url=image_path,
                        path=image_path,
                        confidence=confidence,
                        category=category,
                        tags=result.get('suggested_tags', [])
                    ))
            
            except Exception as e:
                logging.error(f"Error processing image {image_path}: {str(e)}")
                continue
        
        return sorted(matches, key=lambda x: x.confidence, reverse=True)

    def update_user_choice(self, image_match: ImageMatch, user_verified: bool):
        """Update learning data based on user's verification of image matches"""
        try:
            with open(self.learning_data_path, 'r') as f:
                learning_data = json.load(f)
            
            category = image_match.category.lower()
            
            # Update category patterns
            if category not in learning_data['category_patterns']:
                learning_data['category_patterns'][category] = {
                    'positive_examples': [],
                    'negative_examples': []
                }
            
            # Generate image features
            image_features = self._extract_image_features(image_match.path)
            
            # Update patterns based on user verification
            if user_verified:
                learning_data['category_patterns'][category]['positive_examples'].append({
                    'features': image_features,
                    'tags': image_match.tags,
                    'timestamp': datetime.now().isoformat()
                })
            else:
                learning_data['category_patterns'][category]['negative_examples'].append({
                    'features': image_features,
                    'tags': image_match.tags,
                    'timestamp': datetime.now().isoformat()
                })
            
            # Save updated learning data
            self._save_learning_data(learning_data)
            
        except Exception as e:
            logging.error(f"Error updating user choice: {str(e)}")

    # def _generate_image_description(self, image_path: str) -> str:
    #     """Generate a d`escription of the image using AI."""
    #     try:
    #         # Example using a hypothetical vision API
    #         description = vision_api.describe_image(image_path)
    #         return description
    #     except Exception as e:
    #         logging.error(f"Error generating image description for {image_path}: {e}")
    #         return "" # Or` raise the exception if you want to stop processing

    def _extract_image_features(self, image_path: str) -> Dict:
        """Extract features from an image for pattern matching"""
        # This would extract relevant features from the image
        # Placeholder for implementation
        return {}

    def _matches_learned_patterns(self, image_description: str, category_patterns: Dict) -> bool:
        """Check if image matches learned patterns for a category"""
        # This would implement pattern matching logic
        # Placeholder for implementation
        return False