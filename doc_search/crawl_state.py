"""Compatibility shim. Prefer ``doc_search.crawl.state``."""

from .crawl.state import CrawlState, CrawlError

__all__ = ['CrawlState', 'CrawlError']
