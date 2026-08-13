"""Document and HTML extraction.

Depends only on ``doc_search.core``.
"""

from .html import HTMLTextExtractor, extract_text, extract_links
from .dom import (
    Node, Element, Text, DOMTreeBuilder, parse_html,
    extract_text_dom, strip_boilerplate, extract_main_content,
)
from .pdf import PDFExtractor, extract_pdf_text
from .word import WordExtractor, extract_word_text
from .excel import ExcelExtractor, extract_excel_text
from .pptx import PPTXExtractor
from .registry import ExtractorRegistry, create_registry

__all__ = [
    'HTMLTextExtractor',
    'extract_text',
    'extract_links',
    'Node', 'Element', 'Text', 'DOMTreeBuilder', 'parse_html',
    'extract_text_dom', 'strip_boilerplate', 'extract_main_content',
    'PDFExtractor', 'extract_pdf_text',
    'WordExtractor', 'extract_word_text',
    'ExcelExtractor', 'extract_excel_text',
    'PPTXExtractor',
    'ExtractorRegistry', 'create_registry',
]
