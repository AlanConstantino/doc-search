#!/usr/bin/env python3
"""
doc_search - CLI for crawling and searching documentation sites.

Usage:
    python -m doc_search crawl <url> [options]
    python -m doc_search index <site_dir>
    python -m doc_search search <site_dir> <query>
    python -m doc_search interactive <site_dir>
    python -m doc_search serve <site_dir> [--port PORT]
"""

import sys
from .app.cli import main


if __name__ == '__main__':
    sys.exit(main())
