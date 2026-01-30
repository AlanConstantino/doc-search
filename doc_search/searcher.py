"""
Search interface for querying the BM25 index.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from .indexer import BM25Index


class SearchEngine:
    """
    High-level search interface.
    """
    
    def __init__(self, index: BM25Index):
        self.index = index
    
    @classmethod
    def load(cls, index_path: Path) -> 'SearchEngine':
        """Load search engine from saved index."""
        index = BM25Index.load(index_path)
        return cls(index)
    
    def search(
        self, 
        query: str, 
        top_k: int = 10,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search the index.
        
        Args:
            query: Search query
            top_k: Maximum number of results
            min_score: Minimum score threshold
            
        Returns:
            List of result dictionaries
        """
        results = self.index.search(query, top_k=top_k)
        
        if min_score > 0:
            results = [r for r in results if r['score'] >= min_score]
        
        return results
    
    def search_with_context(
        self,
        query: str,
        top_k: int = 10,
        context_length: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Search and include text context for each result.
        
        Note: This requires page files to still be available.
        """
        # For now, just return regular search results
        # Context extraction would require loading original page files
        return self.search(query, top_k=top_k)
    
    def get_document(self, url: str) -> Optional[Dict[str, Any]]:
        """Get document metadata by URL."""
        doc_id = self.index.url_to_id.get(url)
        if doc_id is not None:
            return self.index.documents.get(doc_id)
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get search engine statistics."""
        return self.index.get_stats()


def format_results(results: List[Dict[str, Any]], show_scores: bool = False) -> str:
    """
    Format search results for display.
    
    Args:
        results: List of result dictionaries
        show_scores: Include BM25 scores in output
        
    Returns:
        Formatted string
    """
    if not results:
        return "No results found."
    
    lines = []
    for i, result in enumerate(results, 1):
        title = result.get('title', 'Untitled') or 'Untitled'
        url = result['url']
        description = result.get('description', '')
        score = result.get('score', 0)
        
        # Truncate title if too long
        if len(title) > 80:
            title = title[:77] + '...'
        
        # Truncate description
        if len(description) > 150:
            description = description[:147] + '...'
        
        if show_scores:
            lines.append(f"{i}. [{score:.4f}] {title}")
        else:
            lines.append(f"{i}. {title}")
        
        lines.append(f"   {url}")
        
        if description:
            lines.append(f"   {description}")
        
        lines.append("")
    
    return "\n".join(lines)
