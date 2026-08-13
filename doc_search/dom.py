"""Compatibility shim. Prefer ``doc_search.extract.dom``."""

from .extract.dom import (
    Node, Element, Text, DOMTreeBuilder, parse_html,
    extract_text_dom, strip_boilerplate, extract_main_content, _is_boilerplate,
)

__all__ = [
    'Node', 'Element', 'Text', 'DOMTreeBuilder', 'parse_html',
    'extract_text_dom', 'strip_boilerplate', 'extract_main_content',
    '_is_boilerplate',
]
