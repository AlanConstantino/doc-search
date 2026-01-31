"""
HTML parsing and text extraction.
"""

import re
from html.parser import HTMLParser
from typing import List, Set, Tuple, Optional


class HTMLTextExtractor(HTMLParser):
    """
    Extract text content from HTML, removing scripts, styles, and navigation.
    """
    
    # Tags to completely ignore (including their content)
    IGNORE_TAGS = {'script', 'style', 'noscript', 'svg', 'path', 'iframe'}
    
    # Tags that typically contain navigation/boilerplate
    NAV_TAGS = {'nav', 'header', 'footer', 'aside'}
    
    # Tags that indicate main content
    CONTENT_TAGS = {'main', 'article'}
    
    # Block-level tags that should add whitespace
    BLOCK_TAGS = {
        'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'table', 'tr', 'td', 'th',
        'blockquote', 'pre', 'code', 'section', 'article',
        'header', 'footer', 'nav', 'aside', 'main', 'br', 'hr'
    }
    
    def __init__(self, include_nav: bool = False):
        super().__init__()
        self.include_nav = include_nav
        self.reset_state()
    
    def reset_state(self):
        """Reset extraction state."""
        self.text_parts: List[str] = []
        self.title: Optional[str] = None
        self.description: Optional[str] = None
        self.headings: List[Tuple[int, str]] = []  # (level, text)
        
        self._in_title = False
        self._title_parts: List[str] = []
        self._ignore_depth = 0
        self._nav_depth = 0
        self._tag_stack: List[str] = []
        self._current_heading: Optional[int] = None
        self._heading_parts: List[str] = []
    
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        tag = tag.lower()
        self._tag_stack.append(tag)
        
        # Track ignored sections
        if tag in self.IGNORE_TAGS:
            self._ignore_depth += 1
        
        # Track navigation sections
        if tag in self.NAV_TAGS and not self.include_nav:
            self._nav_depth += 1
        
        # Track title
        if tag == 'title':
            self._in_title = True
            self._title_parts = []
        
        # Track headings
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._current_heading = int(tag[1])
            self._heading_parts = []
        
        # Extract meta description
        if tag == 'meta':
            attrs_dict = dict(attrs)
            name = attrs_dict.get('name', '').lower()
            if name == 'description':
                self.description = attrs_dict.get('content', '')
        
        # Add whitespace for block elements
        if tag in self.BLOCK_TAGS and self.text_parts:
            self.text_parts.append(' ')
    
    def handle_endtag(self, tag: str):
        tag = tag.lower()
        
        # Pop from stack (handle malformed HTML)
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
        
        # Update ignore tracking
        if tag in self.IGNORE_TAGS and self._ignore_depth > 0:
            self._ignore_depth -= 1
        
        # Update nav tracking
        if tag in self.NAV_TAGS and self._nav_depth > 0:
            self._nav_depth -= 1
        
        # Capture title
        if tag == 'title':
            self._in_title = False
            self.title = ''.join(self._title_parts).strip()
        
        # Capture heading
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6') and self._current_heading:
            heading_text = ''.join(self._heading_parts).strip()
            if heading_text:
                self.headings.append((self._current_heading, heading_text))
            self._current_heading = None
        
        # Add whitespace after block elements
        if tag in self.BLOCK_TAGS:
            self.text_parts.append(' ')
    
    def handle_data(self, data: str):
        # Always capture title
        if self._in_title:
            self._title_parts.append(data)
        
        # Capture heading text
        if self._current_heading is not None:
            self._heading_parts.append(data)
        
        # Skip if in ignored section
        if self._ignore_depth > 0:
            return
        
        # Skip if in nav section
        if self._nav_depth > 0:
            return
        
        # Add to text content
        if data.strip():
            self.text_parts.append(data)
    
    def handle_entityref(self, name: str):
        """Handle named entities like &nbsp;"""
        entities = {
            'nbsp': ' ', 'lt': '<', 'gt': '>', 'amp': '&',
            'quot': '"', 'apos': "'", 'copy': '©', 'reg': '®'
        }
        char = entities.get(name, '')
        if char:
            self.handle_data(char)
    
    def handle_charref(self, name: str):
        """Handle numeric character references like &#160;"""
        try:
            if name.startswith('x'):
                char = chr(int(name[1:], 16))
            else:
                char = chr(int(name))
            self.handle_data(char)
        except (ValueError, OverflowError):
            pass
    
    def get_text(self) -> str:
        """Get extracted text, cleaned up."""
        text = ''.join(self.text_parts)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def error(self, message: str):
        """Ignore parse errors for malformed HTML."""
        pass


def extract_text(html: str, include_nav: bool = False) -> dict:
    """
    Extract text and metadata from HTML.
    
    Returns:
        dict with keys: text, title, description, headings
    """
    extractor = HTMLTextExtractor(include_nav=include_nav)
    
    try:
        extractor.feed(html)
    except Exception:
        # Handle malformed HTML gracefully
        pass
    
    return {
        'text': extractor.get_text(),
        'title': extractor.title or '',
        'description': extractor.description or '',
        'headings': extractor.headings
    }


def extract_links(html: str, base_url: str) -> List[str]:
    """
    Extract all links from HTML.
    """
    from .utils import resolve_url, normalize_url, is_valid_url
    
    links = []
    
    # Find all href attributes (quoted or unquoted)
    # Matches: href="...", href='...', href=value (unquoted)
    href_pattern = re.compile(
        r'<a[^>]+href=(?:"([^"]+)"|\'([^\']+)\'|([^\s>]+))',
        re.IGNORECASE
    )
    
    for match in href_pattern.finditer(html):
        # Get whichever group matched (double-quoted, single-quoted, or unquoted)
        href = match.group(1) or match.group(2) or match.group(3)
        
        # Skip anchors, javascript, mailto, etc.
        if href.startswith(('#', 'javascript:', 'mailto:', 'tel:', 'data:')):
            continue
        
        # Resolve relative URLs
        full_url = resolve_url(base_url, href)
        
        if is_valid_url(full_url):
            normalized = normalize_url(full_url)
            links.append(normalized)
    
    return links
