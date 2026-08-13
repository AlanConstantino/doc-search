"""
Multi-site search: search across all crawled sites simultaneously.

Merges results from multiple site indexes, ranked by BM25 score.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from .searcher import SearchEngine, EnhancedSearchEngine
from .cli.commands import DEFAULT_DATA_DIR


def discover_sites(data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Discover all indexed sites in the data directory.
    
    Args:
        data_dir: Directory containing site folders (default: from config / ~/.doc_search/sites/)
        
    Returns:
        List of dicts with 'path', 'url', 'name', 'index_path' keys
    """
    data_dir = data_dir or DEFAULT_DATA_DIR
    
    if not data_dir.exists():
        return []
    
    sites = []
    for site_dir in sorted(data_dir.iterdir()):
        if not site_dir.is_dir():
            continue
        
        # Find index file
        index_path = None
        for candidate in [site_dir / 'index.pkl.gz', site_dir / 'index.json.gz', site_dir / 'index.json']:
            if candidate.exists():
                index_path = candidate
                break
        
        if not index_path:
            continue  # No index, skip
        
        # Load metadata
        url = None
        name = site_dir.name
        metadata_file = site_dir / 'metadata.json'
        if metadata_file.exists():
            try:
                with open(metadata_file, encoding='utf-8') as f:
                    metadata = json.load(f)
                url = metadata.get('url') or metadata.get('source')
                name = metadata.get('site_name') or url or site_dir.name
            except (json.JSONDecodeError, IOError):
                pass
        
        sites.append({
            'path': site_dir,
            'url': url,
            'name': name,
            'hash': site_dir.name,
            'index_path': index_path,
        })
    
    return sites


def filter_sites(
    sites: List[Dict[str, Any]], 
    site_filters: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Filter sites by URL or hash prefix.
    
    Args:
        sites: List of site dicts from discover_sites()
        site_filters: List of URL substrings or hash prefixes to match
        
    Returns:
        Filtered list of sites
    """
    if not site_filters:
        return sites
    
    filtered = []
    for site in sites:
        for f in site_filters:
            f_lower = f.lower()
            # Match by URL substring
            if site.get('url') and f_lower in site['url'].lower():
                filtered.append(site)
                break
            # Match by hash prefix
            if site['hash'].lower().startswith(f_lower):
                filtered.append(site)
                break
            # Match by name substring
            if f_lower in site['name'].lower():
                filtered.append(site)
                break
    
    return filtered


class MultiSiteSearchEngine:
    """
    Search engine that searches across multiple site indexes.
    
    Results are merged and ranked by BM25 score across all sites.
    Each result is annotated with its source site.
    """
    
    def __init__(
        self,
        sites: Optional[List[Dict[str, Any]]] = None,
        data_dir: Optional[Path] = None,
        site_filters: Optional[List[str]] = None,
        enable_spellcheck: bool = True,
        enable_facets: bool = False,
        enable_synonyms: bool = False,
        enable_symspell: bool = False,
        enable_ngram: bool = False,
        synonym_groups=None,
    ):

        """
        Initialize multi-site search engine.
        
        Args:
            sites: Pre-discovered site list (if None, discovers automatically)
            data_dir: Data directory for site discovery
            site_filters: Optional filters to select specific sites
        """
        if sites is None:
            sites = discover_sites(data_dir)
        
        if site_filters:
            sites = filter_sites(sites, site_filters)
        
        self._site_info = sites
        self._engines: Dict[str, SearchEngine] = {}
        self._engine_kwargs = {
            'enable_spellcheck': enable_spellcheck,
            'enable_facets': enable_facets,
            'enable_synonyms': enable_synonyms,
            'enable_symspell': enable_symspell,
            'enable_ngram': enable_ngram,
            'synonym_groups': synonym_groups,
        }
    
    @property
    def site_count(self) -> int:
        """Number of sites available for search."""
        return len(self._site_info)
    
    @property
    def sites(self) -> List[Dict[str, Any]]:
        """List of site info dicts."""
        return list(self._site_info)
    
    def _get_engine(self, site: Dict[str, Any]) -> SearchEngine:
        """Get or load the search engine for a site."""
        key = str(site['index_path'])
        if key not in self._engines:
            self._engines[key] = EnhancedSearchEngine.load(
                site['index_path'],
                **self._engine_kwargs,
            )
        return self._engines[key]
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        highlight: bool = True,
        snippet_length: int = 150,
    ) -> List[Dict[str, Any]]:
        """
        Search across all sites, merging and ranking results by BM25 score.
        
        Args:
            query: Search query
            top_k: Maximum total results to return
            highlight: Highlight query terms in snippets
            snippet_length: Target snippet length
            
        Returns:
            List of result dicts, each with an added 'site' key
        """
        all_results = []

        def _search_one(site):
            engine = self._get_engine(site)
            results = engine.search(
                query,
                top_k=top_k,
                highlight=highlight,
                snippet_length=snippet_length,
            )
            site_label = site.get('url') or site.get('name') or site['hash']
            for r in results:
                r['site'] = site_label
                r['site_hash'] = site['hash']
            return results

        # Parallel per-site search (stdlib threads; release GIL on I/O)
        workers = min(8, max(1, len(self._site_info)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_search_one, s): s for s in self._site_info}
            for fut in as_completed(futures):
                try:
                    all_results.extend(fut.result())
                except Exception:
                    continue

        all_results.sort(key=lambda r: r.get('score', 0), reverse=True)
        return all_results[:top_k]
    
    def search_enhanced(
        self,
        query: str,
        top_k: int = 10,
        highlight: bool = True,
        snippet_length: int = 150,
    ) -> Dict[str, Any]:
        """
        Enhanced multi-site search returning dict with metadata.
        
        Returns:
            Dict with 'results', 'query', 'sites_searched' keys
        """
        results = self.search(
            query, top_k=top_k, highlight=highlight,
            snippet_length=snippet_length,
        )
        
        return {
            'results': results,
            'query': query,
            'sites_searched': len(self._site_info),
            'site_names': [s.get('url') or s['name'] for s in self._site_info],
        }
    
    # Compatibility with server expectations
    last_suggestion = None
    
    def get_spelling_suggestion(self, query: str) -> Optional[str]:
        """Not supported in multi-site mode."""
        return None
    
    def get_facet_counts(self, results=None):
        """Not supported in multi-site mode."""
        return {}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics across all sites."""
        total_docs = 0
        total_terms = 0
        site_stats = []
        
        for site in self._site_info:
            try:
                engine = self._get_engine(site)
                stats = engine.get_stats()
                total_docs += stats.get('total_documents', 0)
                total_terms += stats.get('unique_terms', 0)
                site_stats.append({
                    'name': site.get('url') or site['name'],
                    'hash': site['hash'],
                    'documents': stats.get('total_documents', 0),
                    'terms': stats.get('unique_terms', 0),
                })
            except Exception:
                continue
        
        return {
            'total_sites': len(self._site_info),
            'total_documents': total_docs,
            'total_unique_terms': total_terms,
            'sites': site_stats,
        }
