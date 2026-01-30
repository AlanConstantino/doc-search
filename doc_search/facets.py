"""
Faceted search support - filter results by categories/sections.

Extracts and indexes document facets (sections, types, etc.) for filtering.
"""

from typing import List, Dict, Set, Any, Optional, Tuple
from collections import defaultdict
from pathlib import Path
import json
import re


class FacetExtractor:
    """
    Extract facets from document content.
    
    Domain-agnostic: uses URL path structure directly without
    trying to interpret or categorize document types.
    """
    
    @classmethod
    def extract_section(cls, title: str, headings: List[Tuple[int, str]]) -> str:
        """
        Extract the main section from a document title.
        
        Args:
            title: Document title
            headings: List of (level, text) tuples (currently unused)
            
        Returns:
            Section name (normalized)
        """
        if not title:
            return 'general'
        
        # Try to extract the first significant part of the title
        # Handle common patterns like "Module — Description" or "Topic: Subtitle"
        for separator in ['—', '–', '-', ':', '|']:
            if separator in title:
                parts = title.split(separator)
                section = cls._normalize_section(parts[0])
                if section and len(section) > 1:
                    return section
        
        # Just use first few words of title
        section = cls._normalize_section(title)
        return section if section else 'general'
    
    @classmethod
    def extract_path_facets(cls, url: str) -> List[str]:
        """
        Extract hierarchical facets from URL path.
        
        Args:
            url: Document URL
            
        Returns:
            List of path components as facets
        """
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        
        # Remove file extensions
        path = re.sub(r'\.(html?|php|asp)$', '', path)
        
        # Split into components
        parts = [p for p in path.split('/') if p and not p.startswith('index')]
        
        # Return meaningful parts (skip version numbers, etc.)
        facets = []
        for part in parts:
            # Skip version-like strings
            if re.match(r'^\d+(\.\d+)*$', part):
                continue
            # Skip very short generic parts
            if part in ('docs', 'doc', 'en', 'us'):
                continue
            facets.append(part.lower())
        
        return facets[:3]  # Limit depth
    
    @classmethod
    def _normalize_section(cls, text: str) -> str:
        """Normalize section text to a consistent format."""
        if not text:
            return ''
        
        # Remove special characters and normalize whitespace
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        text = ' '.join(text.split())
        
        # Take first 2-3 words
        words = text.split()[:3]
        return ' '.join(words) if words else ''


class FacetIndex:
    """
    Index for faceted search - maps facet values to document IDs.
    
    Supports multiple facet types (section, type, path, etc.)
    """
    
    def __init__(self):
        """Initialize empty facet index."""
        # facet_type -> facet_value -> set of doc_ids
        self.facets: Dict[str, Dict[str, Set[int]]] = defaultdict(lambda: defaultdict(set))
        
        # doc_id -> dict of facet_type -> facet_value
        self.doc_facets: Dict[int, Dict[str, str]] = {}
    
    def add_document(self, doc_id: int, url: str, title: str, 
                     headings: List[Tuple[int, str]] = None):
        """
        Add a document and extract its facets.
        
        Facets are extracted from:
        - URL path segments (domain-agnostic)
        - Document title
        
        Args:
            doc_id: Document identifier
            url: Document URL
            title: Document title
            headings: List of (level, text) tuples
        """
        headings = headings or []
        
        # Extract facets from URL path (domain-agnostic)
        path_facets = FacetExtractor.extract_path_facets(url)
        section = FacetExtractor.extract_section(title, headings)
        
        # Store facets - use path segments as primary categorization
        facet_dict = {
            'section': section,
        }
        
        # Use first path segment as category, second as subcategory
        if len(path_facets) >= 1:
            facet_dict['category'] = path_facets[0]
        if len(path_facets) >= 2:
            facet_dict['subcategory'] = path_facets[1]
        
        self.doc_facets[doc_id] = facet_dict
        
        # Update facet index
        self.facets['section'][section].add(doc_id)
        
        if len(path_facets) >= 1:
            self.facets['category'][path_facets[0]].add(doc_id)
        if len(path_facets) >= 2:
            self.facets['subcategory'][path_facets[1]].add(doc_id)
    
    def get_facet_values(self, facet_type: str) -> Dict[str, int]:
        """
        Get all values for a facet type with counts.
        
        Args:
            facet_type: The facet type (e.g., 'section', 'type')
            
        Returns:
            Dict mapping facet values to document counts
        """
        if facet_type not in self.facets:
            return {}
        
        return {
            value: len(doc_ids) 
            for value, doc_ids in self.facets[facet_type].items()
        }
    
    def get_facet_counts(self, doc_ids: Set[int]) -> Dict[str, Dict[str, int]]:
        """
        Get facet counts for a set of documents (for search results).
        
        Args:
            doc_ids: Set of document IDs from search results
            
        Returns:
            Dict mapping facet_type -> value -> count
        """
        counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        for doc_id in doc_ids:
            if doc_id in self.doc_facets:
                for facet_type, value in self.doc_facets[doc_id].items():
                    counts[facet_type][value] += 1
        
        return dict(counts)
    
    def filter_by_facet(self, doc_ids: Set[int], facet_type: str, 
                        facet_value: str) -> Set[int]:
        """
        Filter document IDs by a facet value.
        
        Args:
            doc_ids: Set of document IDs to filter
            facet_type: The facet type
            facet_value: The facet value to filter by
            
        Returns:
            Filtered set of document IDs
        """
        if facet_type not in self.facets:
            return doc_ids
        
        if facet_value not in self.facets[facet_type]:
            return set()
        
        facet_docs = self.facets[facet_type][facet_value]
        return doc_ids & facet_docs
    
    def filter_by_facets(self, doc_ids: Set[int], 
                         filters: Dict[str, str]) -> Set[int]:
        """
        Filter document IDs by multiple facet values (AND logic).
        
        Args:
            doc_ids: Set of document IDs to filter
            filters: Dict mapping facet_type -> facet_value
            
        Returns:
            Filtered set of document IDs
        """
        result = doc_ids.copy()
        
        for facet_type, facet_value in filters.items():
            result = self.filter_by_facet(result, facet_type, facet_value)
            if not result:
                break
        
        return result
    
    def get_doc_facets(self, doc_id: int) -> Dict[str, str]:
        """Get facets for a specific document."""
        return self.doc_facets.get(doc_id, {})
    
    def get_all_facet_types(self) -> List[str]:
        """Get all available facet types."""
        return list(self.facets.keys())
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize facet index to dict for storage."""
        return {
            'facets': {
                ftype: {value: list(doc_ids) for value, doc_ids in values.items()}
                for ftype, values in self.facets.items()
            },
            'doc_facets': self.doc_facets
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FacetIndex':
        """Deserialize facet index from dict."""
        index = cls()
        
        for ftype, values in data.get('facets', {}).items():
            for value, doc_ids in values.items():
                index.facets[ftype][value] = set(doc_ids)
        
        index.doc_facets = {
            int(k): v for k, v in data.get('doc_facets', {}).items()
        }
        
        return index
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the facet index."""
        return {
            'facet_types': len(self.facets),
            'total_documents': len(self.doc_facets),
            'facets': {
                ftype: len(values) 
                for ftype, values in self.facets.items()
            }
        }
