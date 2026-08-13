"""
doc_search - A self-contained documentation search tool.

Layered packages (dependencies only point down):

    app        CLI + web UI
      └─ search    engines + optional features
           └─ index    BM25 store
                └─ extract    HTML / PDF / Office
                     └─ core    config, urls, tokenize, constants

Search through large technical documentation websites using BM25 ranking.
Pure Python 3.6+ standard library, no runtime dependencies.
"""

__version__ = "2.7.0"
__author__ = "Alan Constantino"
