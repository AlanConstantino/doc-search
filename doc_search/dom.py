"""
DOM Tree Parser for HTML content extraction.

This module provides a lightweight DOM tree implementation using only Python
stdlib. It enables structure-aware content extraction for better indexing.

Classes:
    Node: Base class for DOM nodes
    Element: HTML element with tag, attributes, and children
    Text: Text content between tags
    DOMTreeBuilder: Builds DOM tree from HTML using HTMLParser

Functions:
    parse_html: Parse HTML string into a DOM tree
    extract_text_dom: Extract text content using DOM tree (main entry point)
"""

from html.parser import HTMLParser
from typing import Dict, List, Optional, Iterator, Tuple, Any, Set
import re


# =============================================================================
# Phase 1: Core Data Structures
# =============================================================================

class Node:
    """
    Base class for DOM nodes.
    
    Attributes:
        parent: Parent element, or None for root nodes.
    """
    
    __slots__ = ('parent',)
    
    def __init__(self) -> None:
        self.parent: Optional['Element'] = None
    
    def remove(self) -> None:
        """Detach this node from its parent."""
        if self.parent is not None:
            self.parent.children.remove(self)
            self.parent = None


class Text(Node):
    """
    Text content between HTML tags.
    
    Attributes:
        content: The text string.
    """
    
    __slots__ = ('content',)
    
    def __init__(self, content: str) -> None:
        super().__init__()
        self.content = content
    
    def __repr__(self) -> str:
        preview = self.content[:30] + '...' if len(self.content) > 30 else self.content
        return f'Text({preview!r})'


class Element(Node):
    """
    HTML element with tag name, attributes, and children.
    
    Attributes:
        tag: Tag name (lowercase).
        attrs: Dictionary of attributes.
        children: List of child nodes (Element or Text).
    """
    
    __slots__ = ('tag', 'attrs', 'children')
    
    def __init__(self, tag: str, attrs: Optional[Dict[str, str]] = None) -> None:
        super().__init__()
        self.tag = tag.lower()
        self.attrs = attrs or {}
        self.children: List[Node] = []
    
    def __repr__(self) -> str:
        return f'Element(<{self.tag}>, {len(self.children)} children)'
    
    def __iter__(self) -> Iterator[Node]:
        """Iterate over direct children."""
        return iter(self.children)
    
    def append(self, node: Node) -> None:
        """Append a child node."""
        node.parent = self
        self.children.append(node)
    
    def find(self, tag: str) -> Optional['Element']:
        """
        Find first descendant element with matching tag name.
        
        Args:
            tag: Tag name to search for (case-insensitive).
        
        Returns:
            First matching Element, or None if not found.
        """
        tag = tag.lower()
        for child in self.children:
            if isinstance(child, Element):
                if child.tag == tag:
                    return child
                result = child.find(tag)
                if result is not None:
                    return result
        return None
    
    def find_all(self, tag: str) -> List['Element']:
        """
        Find all descendant elements with matching tag name.
        
        Args:
            tag: Tag name to search for (case-insensitive).
        
        Returns:
            List of matching Elements.
        """
        tag = tag.lower()
        results: List['Element'] = []
        for child in self.children:
            if isinstance(child, Element):
                if child.tag == tag:
                    results.append(child)
                results.extend(child.find_all(tag))
        return results
    
    def get_text(self, separator: str = ' ') -> str:
        """
        Get all text content from this element and descendants.
        
        Args:
            separator: String to join text pieces (default: single space).
        
        Returns:
            Concatenated text content.
        """
        parts: List[str] = []
        self._collect_text(parts)
        # Join and normalize whitespace
        text = separator.join(parts)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _collect_text(self, parts: List[str]) -> None:
        """Recursively collect text content."""
        for child in self.children:
            if isinstance(child, Text):
                parts.append(child.content)
            elif isinstance(child, Element):
                child._collect_text(parts)
    
    def get_attr(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Get attribute value by name."""
        return self.attrs.get(name, default)
    
    def descendants(self) -> Iterator['Element']:
        """Iterate over all descendant elements (depth-first)."""
        for child in self.children:
            if isinstance(child, Element):
                yield child
                yield from child.descendants()


# =============================================================================
# Phase 2: Tree Builder
# =============================================================================

class DOMTreeBuilder(HTMLParser):
    """
    Build a DOM tree from HTML using stdlib HTMLParser.
    
    Handles malformed HTML gracefully, similar to browser behavior.
    
    Attributes:
        root: The root Element (tag='[document]').
    
    Example:
        >>> builder = DOMTreeBuilder()
        >>> builder.feed('<html><body><p>Hello</p></body></html>')
        >>> builder.root.find('p').get_text()
        'Hello'
    """
    
    # Void elements (self-closing, no end tag)
    VOID_ELEMENTS: Set[str] = {
        'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
        'link', 'meta', 'param', 'source', 'track', 'wbr'
    }
    
    # Block elements (for whitespace handling)
    BLOCK_ELEMENTS: Set[str] = {
        'address', 'article', 'aside', 'blockquote', 'canvas', 'dd', 'div',
        'dl', 'dt', 'fieldset', 'figcaption', 'figure', 'footer', 'form',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hr', 'li', 'main',
        'nav', 'noscript', 'ol', 'p', 'pre', 'section', 'table', 'tfoot',
        'ul', 'video'
    }
    
    def __init__(self) -> None:
        super().__init__()
        self.root = Element('[document]')
        self._stack: List[Element] = [self.root]
    
    @property
    def _current(self) -> Element:
        """Current element (top of stack)."""
        return self._stack[-1]
    
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        """Handle opening tag."""
        tag = tag.lower()
        
        # Convert attrs list to dict
        attr_dict = {k: (v if v is not None else '') for k, v in attrs}
        
        # Create element
        element = Element(tag, attr_dict)
        self._current.append(element)
        
        # Push to stack if not void element
        if tag not in self.VOID_ELEMENTS:
            self._stack.append(element)
    
    def handle_endtag(self, tag: str) -> None:
        """Handle closing tag."""
        tag = tag.lower()
        
        # Don't pop for void elements
        if tag in self.VOID_ELEMENTS:
            return
        
        # Find matching open tag in stack
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                # Pop everything up to and including the matching tag
                self._stack = self._stack[:i]
                return
        
        # No matching tag found - ignore (malformed HTML)
    
    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        """Handle self-closing tag like <br/>."""
        tag = tag.lower()
        attr_dict = {k: (v if v is not None else '') for k, v in attrs}
        element = Element(tag, attr_dict)
        self._current.append(element)
    
    def handle_data(self, data: str) -> None:
        """Handle text content."""
        if data.strip():  # Only add non-empty text
            self._current.append(Text(data))
    
    def handle_entityref(self, name: str) -> None:
        """Handle named entity like &amp;"""
        from html import unescape
        char = unescape(f'&{name};')
        if char.strip():
            self._current.append(Text(char))
    
    def handle_charref(self, name: str) -> None:
        """Handle numeric entity like &#65;"""
        from html import unescape
        char = unescape(f'&#{name};')
        if char.strip():
            self._current.append(Text(char))
    
    def handle_comment(self, data: str) -> None:
        """Ignore comments."""
        pass
    
    def handle_decl(self, decl: str) -> None:
        """Ignore declarations like <!DOCTYPE>."""
        pass


def parse_html(html: str) -> Element:
    """
    Parse HTML string into a DOM tree.
    
    Args:
        html: HTML content to parse.
    
    Returns:
        Root Element of the DOM tree.
    
    Example:
        >>> root = parse_html('<html><body><p>Hello</p></body></html>')
        >>> root.find('p').get_text()
        'Hello'
    """
    builder = DOMTreeBuilder()
    builder.feed(html)
    return builder.root


# =============================================================================
# Phase 3: Content Extraction
# =============================================================================

# Tags to strip (boilerplate and non-content)
BOILERPLATE_TAGS: Set[str] = {
    'script', 'style', 'noscript', 'svg', 'path', 'iframe',
    'nav', 'header', 'footer', 'aside'
}

# ARIA roles that indicate navigation/boilerplate
BOILERPLATE_ROLES: Set[str] = {
    'navigation', 'banner', 'contentinfo', 'complementary', 'search'
}

# Common boilerplate class/id patterns (generic, not framework-specific)
BOILERPLATE_PATTERNS: Set[str] = {
    'nav', 'navbar', 'navigation', 'sidebar', 'menu', 'footer',
    'header', 'breadcrumb'
}

# Tags that indicate main content
MAIN_CONTENT_TAGS: Set[str] = {'main', 'article'}


def _is_boilerplate(element: Element) -> bool:
    """Check if an element is boilerplate based on tag, role, or class/id."""
    # Check tag
    if element.tag in BOILERPLATE_TAGS:
        return True
    
    # Check ARIA role
    role = element.get_attr('role', '').lower()
    if role in BOILERPLATE_ROLES:
        return True
    
    # Check class and id for common patterns
    classes = element.get_attr('class', '').lower()
    elem_id = element.get_attr('id', '').lower()
    
    for pattern in BOILERPLATE_PATTERNS:
        if pattern in classes or pattern in elem_id:
            return True
    
    return False


def strip_boilerplate(element: Element) -> None:
    """
    Remove boilerplate elements (script, style, nav, etc.) in-place.
    
    Detects boilerplate by:
    - Tag name (nav, header, footer, aside, script, style)
    - ARIA role (navigation, banner, contentinfo)
    - Class/ID patterns (sidebar, menu, related, etc.)
    
    Args:
        element: Element to clean (modified in-place).
    """
    # Collect elements to remove (can't modify while iterating)
    to_remove: List[Element] = []
    
    for child in element.children:
        if isinstance(child, Element):
            if _is_boilerplate(child):
                to_remove.append(child)
            else:
                # Recurse into children
                strip_boilerplate(child)
    
    # Remove collected elements
    for child in to_remove:
        child.remove()


def _score_element(element: Element) -> float:
    """
    Score an element by text density (text length / tag count).
    
    Higher scores indicate more content-rich elements with less markup.
    """
    text = element.get_text()
    text_len = len(text)
    
    if text_len == 0:
        return 0.0
    
    # Count descendant elements
    tag_count = sum(1 for _ in element.descendants()) + 1
    
    return text_len / tag_count


def extract_main_content(root: Element) -> Element:
    """
    Find the main content element in the DOM tree.
    
    Algorithm:
    1. Look for <main> tag
    2. Look for <article> tag
    3. Score <div> elements by text density, return highest
    4. Fallback to <body> or root
    
    Args:
        root: Root element of the DOM tree.
    
    Returns:
        Element containing the main content.
    """
    # Try <main> first
    main = root.find('main')
    if main is not None:
        return main
    
    # Try <article>
    article = root.find('article')
    if article is not None:
        return article
    
    # Score all divs and find the best one
    body = root.find('body') or root
    divs = body.find_all('div')
    
    if divs:
        best_div = None
        best_score = 0.0
        
        for div in divs:
            score = _score_element(div)
            if score > best_score:
                best_score = score
                best_div = div
        
        if best_div is not None and best_score > 100:  # Minimum threshold
            return best_div
    
    # Fallback to body
    return body


def _extract_title(root: Element) -> str:
    """Extract title from <title> tag."""
    title_elem = root.find('title')
    if title_elem is not None:
        return title_elem.get_text()
    return ''


def _extract_meta_description(root: Element) -> str:
    """Extract description from <meta name="description">."""
    for meta in root.find_all('meta'):
        name = meta.get_attr('name', '').lower()
        if name == 'description':
            return meta.get_attr('content', '')
    return ''


def _extract_headings(element: Element) -> List[Tuple[int, str]]:
    """
    Extract headings (h1-h6) with their levels.
    
    Returns:
        List of (level, text) tuples.
    """
    headings: List[Tuple[int, str]] = []
    
    for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
        for heading in element.find_all(tag):
            level = int(tag[1])
            text = heading.get_text()
            if text:
                headings.append((level, text))
    
    return headings


def extract_text_dom(html: str, include_nav: bool = False) -> Dict[str, Any]:
    """
    Extract text content from HTML using DOM tree parsing.
    
    This is the main entry point for DOM-based text extraction.
    Returns the same format as the streaming extract_text() function.
    
    Args:
        html: HTML content to parse.
        include_nav: If True, include navigation/boilerplate content.
    
    Returns:
        Dictionary with keys:
        - title: Page title from <title> tag
        - description: Meta description
        - text: Main content text
        - headings: List of (level, text) tuples
    
    Example:
        >>> result = extract_text_dom('<html><title>Test</title><body><p>Hello</p></body></html>')
        >>> result['title']
        'Test'
        >>> result['text']
        'Hello'
    """
    # Build DOM tree
    root = parse_html(html)
    
    # Extract metadata from full document
    title = _extract_title(root)
    description = _extract_meta_description(root)
    
    # Find body (or use root if no body)
    body = root.find('body') or root
    
    # Strip boilerplate if not including nav
    if not include_nav:
        strip_boilerplate(body)
        # Find main content
        main = extract_main_content(body)
    else:
        # Include all content when include_nav=True
        main = body
    
    # Extract text and headings from main content
    text = main.get_text()
    headings = _extract_headings(main)
    
    return {
        'title': title,
        'description': description,
        'text': text,
        'headings': headings
    }
