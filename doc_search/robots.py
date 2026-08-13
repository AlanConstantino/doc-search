"""Compatibility shim. Prefer ``doc_search.crawl.robots``."""

from .crawl.robots import RobotsChecker

__all__ = ['RobotsChecker']
