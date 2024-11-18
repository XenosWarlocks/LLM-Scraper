from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from content_analyzer import ImageMatch


@dataclass
class ParseResult:
    """Data class to hold parsing results"""
    site_id: str
    content_analysis: Dict
    image_matches: List[ImageMatch]
    raw_content: str
    gemini_parse_result: Optional[str] = None
    downloaded_files: List[str] = None
    pdf_links: List[str] = None
    timestamp: str = datetime.now().isoformat()