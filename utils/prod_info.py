from typing import List, Dict, Union, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime

@dataclass
class ProductInfo:
    name: str = "NO_MATCH"
    model_number: str = "NO_MATCH"
    serial_number: str = "NO_MATCH"
    warranty_info: str = "NO_MATCH"
    user_manual: List[str] = field(default_factory=list)
    other_documents: List[str] = field(default_factory=list)
    additional_info: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    url: str = ""
    site_id: str = ""