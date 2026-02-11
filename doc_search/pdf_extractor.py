"""
PDF text extraction using vendored pypdf library.
Extracts text content with heading detection for improved search indexing.

Uses pypdf's visitor pattern to analyze font sizes and detect headings,
enabling field-aware search ranking (title > headings > body).
"""

import re
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from io import BytesIO
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .utils import make_basic_auth_header, create_permissive_ssl_context

# Add vendor directory to path for pypdf import
_vendor_path = Path(__file__).parent.parent / 'vendor'
if str(_vendor_path) not in sys.path:
    sys.path.insert(0, str(_vendor_path))

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PDFExtractor:
    """
    Extract text content from PDF files with heading detection.
    
    Uses pypdf's visitor pattern to analyze font sizes and detect headings
    for improved search ranking. Supports both local files and URLs.
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
        self.ssl_context = create_permissive_ssl_context()
    
    def _get_auth_header(self) -> Optional[str]:
        """Get Basic Auth header if credentials provided."""
        return make_basic_auth_header(auth=self.auth, auth_token=self.auth_token)
    
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
    
    def _detect_headings(
        self,
        text_elements: List[Dict[str, Any]]
    ) -> Tuple[List[Tuple[int, str]], List[str]]:
        """
        Detect headings from text elements using font size analysis.
        
        Heading detection strategy:
        1. Font size > median * 1.2 = heading
        2. Bold fonts on short lines = heading
        3. ALL CAPS short lines = heading
        4. Numbered sections (1.2.3) = heading
        
        Args:
            text_elements: List of dicts with 'text', 'font_size', 'font_name'
            
        Returns:
            Tuple of (headings, body_parts) where headings is list of (level, text)
        """
        if not text_elements:
            return [], []
        
        # Collect font sizes for analysis
        font_sizes = [
            el['font_size'] for el in text_elements
            if el.get('font_size') and el['font_size'] > 0
        ]
        
        # Calculate threshold for heading detection
        if font_sizes:
            sorted_sizes = sorted(font_sizes)
            median_size = sorted_sizes[len(sorted_sizes) // 2]
            heading_threshold = median_size * 1.2  # 20% larger than median
            large_heading_threshold = median_size * 1.4  # 40% larger = h1
        else:
            # Fallback thresholds when no font info available
            heading_threshold = 14.0
            large_heading_threshold = 18.0
            median_size = 12.0
        
        headings = []
        body_parts = []
        
        # Pattern for numbered sections like "1.2.3 Section Title"
        section_pattern = re.compile(r'^(\d+\.)+\d*\s+\w')
        
        for el in text_elements:
            text = el.get('text', '').strip()
            if not text:
                continue
            
            font_size = el.get('font_size', 0) or 0
            font_name = el.get('font_name', '') or ''
            
            is_heading = False
            level = 2  # Default heading level
            
            # Font size based detection (most reliable)
            if font_size > 0:
                if font_size > large_heading_threshold:
                    is_heading = True
                    level = 1
                elif font_size > heading_threshold:
                    is_heading = True
                    level = 2
            
            # Bold font detection (for short lines only)
            if not is_heading and 'Bold' in font_name and len(text) < 100:
                is_heading = True
                level = 2
            
            # ALL CAPS detection (short lines only, at least 3 words or chars)
            if not is_heading and len(text) < 80 and len(text) > 5:
                if text.isupper() and any(c.isalpha() for c in text):
                    is_heading = True
                    level = 2
            
            # Numbered section detection (e.g., "1.2 Methods", "3.4.1 Results")
            if not is_heading and section_pattern.match(text):
                is_heading = True
                # Determine level by number of dots
                dots = text.split()[0].count('.')
                level = min(dots + 1, 3)  # Cap at level 3
            
            if is_heading:
                # Clean up heading text
                clean_text = ' '.join(text.split())  # Normalize whitespace
                if len(clean_text) > 200:
                    # Too long to be a heading, treat as body
                    body_parts.append(text)
                else:
                    headings.append((level, clean_text))
            else:
                body_parts.append(text)
        
        return headings, body_parts
    
    def _extract_outline_headings(
        self,
        outline: Any,
        level: int = 1
    ) -> List[Tuple[int, str]]:
        """
        Extract headings from PDF outline/TOC (bookmarks).
        
        Args:
            outline: PDF outline structure (can be nested)
            level: Current nesting level
            
        Returns:
            List of (level, text) tuples
        """
        headings = []
        
        if outline is None:
            return headings
        
        try:
            if isinstance(outline, list):
                for item in outline:
                    if isinstance(item, list):
                        # Nested outline - recurse with increased level
                        headings.extend(self._extract_outline_headings(item, level + 1))
                    elif hasattr(item, 'title'):
                        # Outline item with title
                        title = str(item.title).strip()
                        if title:
                            headings.append((min(level, 3), title))
            elif hasattr(outline, 'title'):
                title = str(outline.title).strip()
                if title:
                    headings.append((min(level, 3), title))
        except Exception:
            # Outline parsing can fail on malformed PDFs
            pass
        
        return headings
    
    def _extract_with_visitor(
        self,
        reader: PdfReader
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Extract text from PDF using visitor pattern for font info.
        
        Args:
            reader: PdfReader instance
            
        Returns:
            Tuple of (text_elements, fallback_text)
        """
        text_elements = []
        fallback_parts = []
        
        for page_num, page in enumerate(reader.pages):
            try:
                # Try visitor-based extraction first
                page_elements = []
                
                def visitor(text, cm, tm, font_dict, font_size):
                    """Visitor callback to collect text with font info."""
                    if text and text.strip():
                        font_name = ''
                        if font_dict:
                            # Extract font name from font dictionary
                            try:
                                font_name = str(font_dict.get('/BaseFont', ''))
                            except Exception:
                                pass
                        
                        page_elements.append({
                            'text': text.strip(),
                            'font_size': font_size if font_size else 0,
                            'font_name': font_name,
                            'page': page_num + 1,
                        })
                
                # Extract with visitor
                page.extract_text(visitor_text=visitor)
                text_elements.extend(page_elements)
                
                # Also get plain text for fallback
                plain_text = page.extract_text()
                if plain_text:
                    fallback_parts.append(plain_text)
                    
            except Exception as e:
                # Fall back to simple extraction on error
                try:
                    page_text = page.extract_text()
                    if page_text:
                        fallback_parts.append(page_text)
                        # Add as single element without font info
                        text_elements.append({
                            'text': page_text,
                            'font_size': 0,
                            'font_name': '',
                            'page': page_num + 1,
                        })
                except Exception:
                    fallback_parts.append(f"[Page {page_num + 1}: extraction failed]")
        
        fallback_text = '\n\n'.join(fallback_parts)
        return text_elements, fallback_text
    
    def _extract_from_reader(
        self,
        reader: PdfReader,
        title_fallback: str = ''
    ) -> Dict[str, Any]:
        """
        Extract text and headings from a PdfReader instance.
        
        Args:
            reader: PdfReader instance
            title_fallback: Fallback title if none found
            
        Returns:
            Dict with text, title, headings, pages, metadata, error
        """
        result = {
            'text': '',
            'title': '',
            'headings': [],
            'pages': 0,
            'metadata': {},
            'error': None
        }
        
        try:
            result['pages'] = len(reader.pages)
            
            # Extract metadata
            if reader.metadata:
                result['metadata'] = {
                    'title': reader.metadata.get('/Title', ''),
                    'author': reader.metadata.get('/Author', ''),
                    'subject': reader.metadata.get('/Subject', ''),
                    'creator': reader.metadata.get('/Creator', ''),
                }
                result['title'] = result['metadata'].get('title', '') or ''
            
            # Extract text with font information
            text_elements, fallback_text = self._extract_with_visitor(reader)
            
            # Detect headings from font analysis
            detected_headings, body_parts = self._detect_headings(text_elements)
            
            # Extract outline/TOC headings
            outline_headings = []
            try:
                if reader.outline:
                    outline_headings = self._extract_outline_headings(reader.outline)
            except Exception:
                pass
            
            # Combine headings (outline first, then detected)
            # Deduplicate by normalizing and comparing
            seen_headings = set()
            combined_headings = []
            
            for level, text in outline_headings + detected_headings:
                normalized = text.lower().strip()
                if normalized not in seen_headings and len(normalized) > 1:
                    seen_headings.add(normalized)
                    combined_headings.append((level, text))
            
            result['headings'] = combined_headings
            
            # Use body parts if we have them, otherwise fallback
            if body_parts:
                result['text'] = '\n\n'.join(body_parts)
            else:
                result['text'] = fallback_text
            
            # Determine title
            if not result['title']:
                # Try first h1 heading
                h1_headings = [h for h in combined_headings if h[0] == 1]
                if h1_headings:
                    result['title'] = h1_headings[0][1]
                elif combined_headings:
                    result['title'] = combined_headings[0][1]
                elif title_fallback:
                    result['title'] = title_fallback
                    
        except PdfReadError as e:
            result['error'] = f"PDF read error: {e}"
        except Exception as e:
            result['error'] = f"Extraction error: {e}"
        
        return result
    
    def extract_from_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract text and headings from a local PDF file.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            dict with 'text', 'title', 'headings', 'pages', 'metadata', 'error'
        """
        result = {
            'text': '',
            'title': '',
            'headings': [],
            'pages': 0,
            'metadata': {},
            'error': None
        }
        
        try:
            reader = PdfReader(file_path)
            result = self._extract_from_reader(reader, title_fallback=file_path.stem)
        except PdfReadError as e:
            result['error'] = f"PDF read error: {e}"
        except Exception as e:
            result['error'] = f"Extraction error: {e}"
        
        return result
    
    def extract_from_bytes(self, pdf_bytes: bytes, title_fallback: str = '') -> Dict[str, Any]:
        """
        Extract text and headings from PDF bytes (already fetched content).
        
        Args:
            pdf_bytes: Raw PDF bytes
            title_fallback: Fallback title if no metadata title found
            
        Returns:
            dict with 'text', 'title', 'headings', 'pages', 'metadata', 'error'
        """
        result = {
            'text': '',
            'title': '',
            'headings': [],
            'pages': 0,
            'metadata': {},
            'error': None
        }
        
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            result = self._extract_from_reader(reader, title_fallback=title_fallback)
        except PdfReadError as e:
            result['error'] = f"PDF read error: {e}"
        except Exception as e:
            result['error'] = f"Extraction error: {e}"
        
        return result
    
    def extract_from_url(self, url: str) -> Dict[str, Any]:
        """
        Extract text and headings from a PDF at a URL.
        
        Args:
            url: URL to the PDF file
            
        Returns:
            dict with 'text', 'title', 'headings', 'pages', 'metadata', 'error'
        """
        result = {
            'text': '',
            'title': '',
            'headings': [],
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
            from urllib.parse import urlparse
            path = urlparse(url).path
            title_fallback = Path(path).stem
            
            reader = PdfReader(BytesIO(pdf_bytes))
            result = self._extract_from_reader(reader, title_fallback=title_fallback)
        except PdfReadError as e:
            result['error'] = f"PDF read error: {e}"
        except Exception as e:
            result['error'] = f"Extraction error: {e}"
        
        return result
    
    def extract(self, source: str) -> Dict[str, Any]:
        """
        Extract text and headings from a PDF (auto-detect file vs URL).
        
        Args:
            source: File path or URL
            
        Returns:
            dict with 'text', 'title', 'headings', 'pages', 'metadata', 'error'
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
    parser.add_argument('--headings', action='store_true', help='Show detected headings')
    args = parser.parse_args()
    
    extractor = PDFExtractor()
    result = extractor.extract(args.source)
    
    if args.json:
        import json
        # Convert headings tuples to lists for JSON
        result['headings'] = [list(h) for h in result['headings']]
        print(json.dumps(result, indent=2))
    else:
        if result['error']:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
        print(f"Title: {result['title']}")
        print(f"Pages: {result['pages']}")
        if args.headings or result['headings']:
            print(f"\nHeadings ({len(result['headings'])}):")
            for level, text in result['headings'][:20]:  # Show first 20
                indent = "  " * (level - 1)
                print(f"  {indent}[H{level}] {text[:80]}")
            if len(result['headings']) > 20:
                print(f"  ... and {len(result['headings']) - 20} more")
        print(f"\n{'-'*50}\n")
        print(result['text'][:2000])
        if len(result['text']) > 2000:
            print(f"\n... ({len(result['text']) - 2000} more characters)")
