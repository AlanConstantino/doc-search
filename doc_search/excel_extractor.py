"""Compatibility shim. Prefer ``doc_search.extract.excel``."""

from .extract.excel import ExcelExtractor, extract_excel_text

__all__ = ['ExcelExtractor', 'extract_excel_text']
