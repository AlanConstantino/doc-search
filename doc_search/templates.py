"""
HTML page rendering for the doc-search web UI.

Provides render_page() which builds the complete HTML page.
"""

import html as _html
import re
import urllib.parse
from typing import Optional, List, Dict, Any

from . import __version__
from .server import CSS, JAVASCRIPT, _e, _doc_icon, _file_url_to_serve_url


def escape(text: str) -> str:
    """HTML escape text."""
    return _html.escape(str(text)) if text else ""


def highlight_snippet(snippet: str) -> str:
    """Convert **term** markers to <mark> elements."""
    if not snippet:
        return ""
    result = escape(snippet)
    result = re.sub(r'\*\*([^*]+)\*\*', r'<mark>\1</mark>', result)
    return result


def render_page(
    query: str = "",
    results: Optional[List[Dict[str, Any]]] = None,
    elapsed_ms: float = 0,
    stats: Optional[Dict[str, Any]] = None,
    show_scores: bool = True,
    page: int = 1,
    per_page: int = 10,
    total_results: int = 0,
    suggestion: Optional[str] = None,
    facets: Optional[Dict[str, Dict[str, int]]] = None,
    active_facet: Optional[str] = None,
    total_unfiltered: int = 0,
    sort_by: str = "relevance",
    exact_match: bool = False,
    theme: str = "dark",
    global_max_score: Optional[float] = None,
    no_javascript: bool = False
) -> str:
    """Render the full HTML page."""
    from .server import render_page as _original
    return _original(
        query=query, results=results, elapsed_ms=elapsed_ms, stats=stats,
        show_scores=show_scores, page=page, per_page=per_page,
        total_results=total_results, suggestion=suggestion, facets=facets,
        active_facet=active_facet, total_unfiltered=total_unfiltered,
        sort_by=sort_by, exact_match=exact_match, theme=theme,
        global_max_score=global_max_score, no_javascript=no_javascript
    )
