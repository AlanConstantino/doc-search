"""
PDF text extraction using vendored pypdf library.
Extracts text content from PDF files for indexing.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any
from io import BytesIO
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import ssl
import base64

# Add vendor directory to path for PyPDF2 import
_vendor_path = Path(__file__).parent.parent / 'vendor'
if str(_vendor_path) not in sys.path:
    sys.path.insert(0, str(_vendor_path))

# Suppress PyPDF2 deprecation warning (we're vendoring it intentionally)
import warnings
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from PyPDF2 import PdfReader
    from PyPDF2.errors import PdfReadError


class PDFExtractor:
    """
    Extract text content from PDF files.
    
    Supports both local files and URLs.
    """
    
    def __init__(
        self,
        timeout: float = 30.0,
        user_agent: str = "DocSearchBot/1.2",
        auth: Optional[tuple] = None,  # (username, password)
        auth_token: Optional[str] = None,  # Pre-encoded Base64 token
    ):
        self.timeout = timeout
        self.user_agent = user_agent
        self.auth = auth
        self.auth_token = auth_token
        
        # SSL context for self-signed certs
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
    
    def _get_auth_header(self) -> Optional[str]:
        """Get Basic Auth header if credentials provided."""
        if self.auth_token:
            token = self.auth_token
            if token.lower().startswith('basic '):
                token = token[6:]
            return f"Basic {token}"
        if self.auth:
            username, password = self.auth
            credentials = f"{username}:{password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            return f"Basic {encoded}"
        return None
    
    def _fetch_pdf(self, url: str) -> Optional[bytes]:
        """Fetch PDF bytes from URL."""
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/pdf,*/*',
        }
        
        auth_header = self._get_auth_header()
        if auth_header:
            headers['Authorization'] = auth_header
        
        request = Request(url, headers=headers)
        
        try:
            response = urlopen(
                request, 
                timeout=self.timeout, 
                context=self.ssl_context
            )
            return response.read()
        except (HTTPError, URLError) as e:
            return None
        except Exception:
            return None
    
    def extract_from_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract text from a local PDF file.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            dict with 'text', 'title', 'pages', 'metadata', 'error'
        """
        result = {
            'text': '',
            'title': '',
            'pages': 0,
            'metadata': {},
            'error': None
        }
        
        try:
            reader = PdfReader(file_path)
            result['pages'] = len(reader.pages)
            
            # Extract metadata
            if reader.metadata:
                result['metadata'] = {
                    'title': reader.metadata.get('/Title', ''),
                    'author': reader.metadata.get('/Author', ''),
                    'subject': reader.metadata.get('/Subject', ''),
                    'creator': reader.metadata.get('/Creator', ''),
                }
                result['title'] = result['metadata'].get('title', '')
            
            # Extract text from all pages
            text_parts = []
            for i, page in enumerate(reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                except Exception as e:
                    # Some pages may fail, continue with others
                    text_parts.append(f"[Page {i+1}: extraction failed]")
            
            result['text'] = '\n\n'.join(text_parts)
            
            # Use filename as title if no metadata title
            if not result['title']:
                result['title'] = file_path.stem
                
        except PdfReadError as e:
            result['error'] = f"PDF read error: {e}"
        except Exception as e:
            result['error'] = f"Extraction error: {e}"
        
        return result
    
    def extract_from_url(self, url: str) -> Dict[str, Any]:
        """
        Extract text from a PDF at a URL.
        
        Args:
            url: URL to the PDF file
            
        Returns:
            dict with 'text', 'title', 'pages', 'metadata', 'error'
        """
        result = {
            'text': '',
            'title': '',
            'pages': 0,
            'metadata': {},
            'error': None
        }
        
        # Fetch PDF bytes
        pdf_bytes = self._fetch_pdf(url)
        if pdf_bytes is None:
            result['error'] = "Failed to fetch PDF"
            return result
        
        try:
            # Read from bytes
            reader = PdfReader(BytesIO(pdf_bytes))
            result['pages'] = len(reader.pages)
            
            # Extract metadata
            if reader.metadata:
                result['metadata'] = {
                    'title': reader.metadata.get('/Title', ''),
                    'author': reader.metadata.get('/Author', ''),
                    'subject': reader.metadata.get('/Subject', ''),
                    'creator': reader.metadata.get('/Creator', ''),
                }
                result['title'] = result['metadata'].get('title', '')
            
            # Extract text from all pages
            text_parts = []
            for i, page in enumerate(reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                except Exception:
                    text_parts.append(f"[Page {i+1}: extraction failed]")
            
            result['text'] = '\n\n'.join(text_parts)
            
            # Use URL filename as title if no metadata title
            if not result['title']:
                from urllib.parse import urlparse
                path = urlparse(url).path
                result['title'] = Path(path).stem
                
        except PdfReadError as e:
            result['error'] = f"PDF read error: {e}"
        except Exception as e:
            result['error'] = f"Extraction error: {e}"
        
        return result
    
    def extract(self, source: str) -> Dict[str, Any]:
        """
        Extract text from a PDF (auto-detect file vs URL).
        
        Args:
            source: File path or URL
            
        Returns:
            dict with 'text', 'title', 'pages', 'metadata', 'error'
        """
        if source.startswith(('http://', 'https://')):
            return self.extract_from_url(source)
        else:
            return self.extract_from_file(Path(source))


def extract_pdf_text(source: str, **kwargs) -> str:
    """
    Convenience function to extract just the text from a PDF.
    
    Args:
        source: File path or URL to PDF
        **kwargs: Passed to PDFExtractor
        
    Returns:
        Extracted text or empty string on failure
    """
    extractor = PDFExtractor(**kwargs)
    result = extractor.extract(source)
    return result.get('text', '')


# CLI for testing
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract text from PDF files')
    parser.add_argument('source', help='PDF file path or URL')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()
    
    extractor = PDFExtractor()
    result = extractor.extract(args.source)
    
    if args.json:
        import json
        print(json.dumps(result, indent=2))
    else:
        if result['error']:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
        print(f"Title: {result['title']}")
        print(f"Pages: {result['pages']}")
        print(f"\n{'-'*50}\n")
        print(result['text'])
