"""Pretty-print search results for the CLI (ANSI colors)."""

import re
from typing import List, Dict, Any, Optional, Set

from ..terminal import (
    Colors, highlight_match, style_title, style_url, style_score,
    style_number, style_info, style_success,
)
from ...search.snippets import _compile_terms_pattern
from ...core.constants import MAX_TITLE_LENGTH, MAX_SNIPPET_LENGTH


def highlight_terms_ansi(text: str, terms: Set[str]) -> str:
    """
    Highlight search terms in text using ANSI color codes.
    """
    if not terms or not text:
        return text

    cleaned = {str(t).lower().strip() for t in terms if t and str(t).strip()}
    cleaned = {t for t in cleaned if t and not t.endswith('*') and (len(t) >= 2 or t.isdigit())}
    if not cleaned:
        return text

    terms_frozen = frozenset(cleaned)
    pattern = _compile_terms_pattern(terms_frozen)

    def replacer(match):
        return highlight_match(match.group(0))

    return pattern.sub(replacer, text)


def format_results(
    results: List[Dict[str, Any]], 
    show_scores: bool = False,
    query_terms: Optional[Set[str]] = None,
    elapsed_ms: Optional[float] = None,
    colorize_output: bool = True,
    start_index: int = 0
) -> str:
    """
    Format search results for display with beautiful ANSI colors.
    
    Args:
        results: List of result dictionaries
        show_scores: Include BM25 scores in output
        query_terms: Set of query terms for ANSI highlighting (optional)
        elapsed_ms: Search time in milliseconds (optional)
        colorize_output: Use ANSI colors (default: True)
        start_index: Starting index for result numbering (for pagination)
        
    Returns:
        Formatted string
    """
    if not results:
        if colorize_output:
            return style_info("No results found.")
        return "No results found."
    
    lines = []
    
    # Performance header
    if elapsed_ms is not None:
        perf_line = f"Found {len(results)} results in {elapsed_ms:.1f}ms"
        if colorize_output:
            lines.append(style_success(f"✓ {perf_line}"))
        else:
            lines.append(perf_line)
        lines.append("")
    
    # Compute max score for percentage display
    max_score = max((r.get('score', 0) for r in results), default=1.0)
    if max_score <= 0:
        max_score = 1.0
    
    for i, result in enumerate(results, start_index + 1):
        title = result.get('title', 'Untitled') or 'Untitled'
        url = result['url']
        # Prefer snippet (with highlighting) over description
        snippet = result.get('snippet', '') or result.get('description', '')
        score = result.get('score', 0)
        score_pct = int((score / max_score) * 100)
        
        # Truncate title if too long
        if len(title) > MAX_TITLE_LENGTH:
            title = title[:MAX_TITLE_LENGTH - 3] + '...'
        
        # Collapse newlines for terminal display (HTML handles this via CSS)
        snippet = re.sub(r'\s*\n\s*', ' ', snippet).strip()
        
        # Truncate snippet
        if len(snippet) > MAX_SNIPPET_LENGTH:
            snippet = snippet[:MAX_SNIPPET_LENGTH - 3] + '...'
        
        # Apply ANSI highlighting to snippet if we have query terms
        if colorize_output and query_terms and snippet:
            # Convert **term** markers to ANSI codes
            snippet = re.sub(
                r'\*\*([^*]+)\*\*',
                lambda m: highlight_match(m.group(1)),
                snippet
            )
        
        # Doc type badge for all result types
        doc_type = result.get('doc_type', 'html') or 'html'
        type_colors = {
            'pdf': Colors.RED,
            'xlsx': Colors.GREEN,
            'docx': Colors.BLUE,
            'pptx': Colors.ORANGE,
            'html': Colors.DIM,
        }
        type_labels = {
            'pdf': 'PDF',
            'xlsx': 'XLSX',
            'docx': 'DOCX',
            'pptx': 'PPTX',
            'html': 'WEB',
        }
        color = type_colors.get(doc_type, Colors.YELLOW)
        label = type_labels.get(doc_type, doc_type.upper())
        type_badge = f" {color}[{label}]{Colors.RESET}"
        type_badge_plain = f" [{label}]"
        
        # Build the result lines with colors
        if colorize_output:
            if show_scores:
                lines.append(f"{style_number(i)} {style_score(score)} {Colors.DIM}({score_pct}%){Colors.RESET} {style_title(title)}{type_badge}")
            else:
                lines.append(f"{style_number(i)} {style_title(title)}{type_badge}")
            
            lines.append(f"   {style_url(url)}")
            
            if snippet:
                lines.append(f"   {snippet}")
        else:
            # Plain text output
            if show_scores:
                lines.append(f"{i}. [{score:.4f}] ({score_pct}%) {title}{type_badge_plain}")
            else:
                lines.append(f"{i}. {title}{type_badge_plain}")
            
            lines.append(f"   {url}")
            
            if snippet:
                lines.append(f"   {snippet}")
        
        lines.append("")
    
    return "\n".join(lines)

