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
    
    Identifies sections, document types, and other filterable categories.
    """
    
    # Common documentation section patterns
    SECTION_PATTERNS = [
        # Python docs style
        (r'^[\w\s]+\s+—\s+(.+)$', 1),  # "module — Description"
        # Generic heading styles
        (r'^(?:Chapter|Section|Part)\s+\d+[:.]\s*(.+)$', 1),
    ]
    
    # Common documentation types based on URL patterns
    DOC_TYPE_PATTERNS = [
        (r'/tutorial[s]?/', 'tutorial'),
        (r'/guide[s]?/', 'guide'),
        (r'/reference/', 'reference'),
        (r'/api/', 'api'),
        (r'/howto/', 'howto'),
        (r'/faq/', 'faq'),
        (r'/example[s]?/', 'examples'),
        (r'/library/', 'library'),
        (r'/module[s]?/', 'module'),
        (r'/class/', 'class'),
        (r'/function[s]?/', 'function'),
        (r'/glossary/', 'glossary'),
        (r'/changelog/', 'changelog'),
        (r'/release/', 'release'),
    ]
    
    @classmethod
    def extract_section(cls, title: str, headings: List[Tuple[int, str]]) -> str:
        """
        Extract the main section/category from a document.
        
        Args:
            title: Document title
            headings: List of (level, text) tuples
            
        Returns:
            Section name (normalized)
        """
        # Try to get section from h1 or first heading
        for level, text in headings:
            if level == 1:
                # Use h1 as section
                section = cls._normalize_section(text)
                if section:
                    return section
        
        # Fall back to title
        if title:
            # Try to extract module/class name from title
            # e.g., "string — Common string operations" -> "string"
            match = re.match(r'^([\w\.]+)\s*[—–-]', title)
            if match:
                return match.group(1).lower()
            
            # Take first significant word from title
            section = cls._normalize_section(title)
            if section:
                return section
        
        return 'general'
    
    @classmethod
    def extract_doc_type(cls, url: str, title: str = '') -> str:
        """
        Extract document type from URL and title.
        
        Args:
            url: Document URL
            title: Document title
            
        Returns:
            Document type category
        """
        url_lower = url.lower()
        
        # Check URL patterns
        for pattern, doc_type in cls.DOC_TYPE_PATTERNS:
            if re.search(pattern, url_lower):
                return doc_type
        
        # Check title for type hints
        title_lower = title.lower()
        if 'tutorial' in title_lower:
            return 'tutorial'
        if 'reference' in title_lower or 'api' in title_lower:
            return 'reference'
        if 'how to' in title_lower or 'howto' in title_lower:
            return 'howto'
        if 'example' in title_lower:
            return 'examples'
        
        return 'documentation'
    
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
        
        Args:
            doc_id: Document identifier
            url: Document URL
            title: Document title
            headings: List of (level, text) tuples
        """
        headings = headings or []
        
        # Extract facets
        section = FacetExtractor.extract_section(title, headings)
        doc_type = FacetExtractor.extract_doc_type(url, title)
        path_facets = FacetExtractor.extract_path_facets(url)
        
        # Store facets
        facet_dict = {
            'section': section,
            'type': doc_type,
        }
        
        if path_facets:
            facet_dict['category'] = path_facets[0]
        
        self.doc_facets[doc_id] = facet_dict
        
        # Update facet index
        self.facets['section'][section].add(doc_id)
        self.facets['type'][doc_type].add(doc_id)
        
        if path_facets:
            self.facets['category'][path_facets[0]].add(doc_id)
    
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
