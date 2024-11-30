from urllib.parse import urlparse, urljoin, quote
import tldextract
import re

class URLValidator:
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Check if the provided URL is valid."""
        try:
            result = urlparse(url)
            ext = tldextract.extract(url)
            
            # Ensure URL has a valid scheme, netloc, and top-level domain (TLD)
            return all([result.scheme in ['http', 'https'], result.netloc]) and ext.suffix
        except Exception:
            return False

    @staticmethod
    def sanitize_url(url: str) -> str:
        """Sanitize and clean the URL."""
        # Remove non-printable characters and strip leading/trailing whitespace
        sanitized = "".join(c for c in url.strip() if c.isprintable())
        # Replace spaces with %20
        sanitized = quote(sanitized, safe="/:?=&")
        return sanitized

    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize the URL by removing redundant slashes."""
        # Ensure the URL is sanitized first
        url = URLValidator.sanitize_url(url)
        
        # Remove duplicate slashes (except after the scheme)
        url = re.sub(r'(?<!:)//+', '/', url)
        
        # Ensure URL starts with http or https
        if not urlparse(url).scheme:
            url = 'http://' + url
        
        return url

    @staticmethod
    def is_absolute_url(url: str) -> bool:
        """Check if a URL is absolute."""
        return bool(urlparse(url).scheme and urlparse(url).netloc)

    @staticmethod
    def resolve_relative_url(base_url: str, relative_url: str) -> str:
        """Resolve relative URLs to absolute ones."""
        if not URLValidator.is_absolute_url(relative_url):
            return urljoin(base_url, relative_url)
        return relative_url