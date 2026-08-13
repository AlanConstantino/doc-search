"""Application layer: CLI, web UI, terminal formatting.

Depends on search / crawl / index / extract / core. Nothing below may import app.
"""

from .cli import main, create_parser
from .server import run_server, SearchHandler, render_page

__all__ = ['main', 'create_parser', 'run_server', 'SearchHandler', 'render_page']
