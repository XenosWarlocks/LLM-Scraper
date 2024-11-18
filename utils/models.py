from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class BatchProcessingResult:
    """Stores results from batch processing operations."""
    url: str
    status: str
    downloaded_files: Dict[str, List[str]]
    parsed_content: str
    raw_content: str
    error: Optional[str] = None
    model_number: Optional[str] = None