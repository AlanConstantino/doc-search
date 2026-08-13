"""Compatibility shim. Prefer ``doc_search.app.cli``."""

from ..app.cli import main, create_parser

__all__ = ['main', 'create_parser']
