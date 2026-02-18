"""
Title-based suggestion engine for search autocomplete.

Suggests page titles, document filenames, and section headings
instead of raw index terms. Provides a more useful autocomplete
experience in the web UI.

Falls back to word-level suggestions when no title matches are found.
"""

import json
import gzip
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple


# Headings to skip (navigation, boilerplate)
_SKIP_HEADINGS = {
    'navigation', 'table of contents', 'contents', 'menu',
    'previous topic', 'next topic', 'this page', 'see also',
    'references', 'external links', 'footnotes', 'notes',
    'sidebar', 'breadcrumb', 'footer', 'header',
}

# Min heading length to be useful as a suggestion
_MIN_HEADING_LEN = 4

# Max heading level to index (h1-h3 are useful, h4+ are too granular)
_MAX_HEADING_LEVEL = 3


class TitleSuggester:
    """
    Indexes page titles and headings for autocomplete suggestions.
    
    Each entry has:
    - text: the suggestion text (title or heading)
    - doc_type: web/pdf/docx/xlsx
    - url: the page URL
    - weight: relevance weight (titles > h1 > h2 > h3)
    """
    
    def __init__(self):
        self.entries: List[Dict] = []
        # Lowercase text -> index for dedup
        self._seen: set = set()
    
    def add_page(self, title: str, url: str, doc_type: str = 'html',
                 headings: Optional[List] = None):
        """
        Add a page's title and headings to the suggestion index.
        
        Args:
            title: Page title
            url: Page URL
            doc_type: Document type (html, pdf, docx, xlsx)
            headings: List of [level, text] pairs
        """
        # Add title (highest weight)
        if title and len(title.strip()) >= _MIN_HEADING_LEN:
            clean_title = self._clean_text(title)
            if clean_title and clean_title.lower() not in self._seen:
                self._seen.add(clean_title.lower())
                self.entries.append({
                    'text': clean_title,
                    'doc_type': doc_type,
                    'url': url,
                    'weight': 100,
                })
        
        # Add headings (lower weight based on level)
        if headings:
            for heading in headings:
                if not isinstance(heading, (list, tuple)) or len(heading) < 2:
                    continue
                level, text = heading[0], heading[1]
                if not isinstance(level, int) or level > _MAX_HEADING_LEVEL:
                    continue
                if not text or len(text.strip()) < _MIN_HEADING_LEN:
                    continue
                
                clean = self._clean_text(text)
                if not clean:
                    continue
                if clean.lower() in self._seen:
                    continue
                if clean.lower() in _SKIP_HEADINGS:
                    continue
                
                self._seen.add(clean.lower())
                # h1=80, h2=60, h3=40
                weight = max(10, 100 - level * 20)
                self.entries.append({
                    'text': clean,
                    'doc_type': doc_type,
                    'url': url,
                    'weight': weight,
                })
    
    def _clean_text(self, text: str) -> str:
        """Clean suggestion text: strip whitespace, pilcrows, numbering."""
        text = text.strip()
        # Remove trailing pilcrow (¶) from headings
        text = text.rstrip('¶').strip()
        # Remove leading section numbers like "18.5.9." or "1.2.3"
        text = re.sub(r'^\d+(\.\d+)*\.?\s*', '', text)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def suggest(self, prefix: str, max_suggestions: int = 8) -> List[Dict]:
        """
        Get title/heading suggestions matching a prefix.
        
        Args:
            prefix: Search prefix (case-insensitive)
            max_suggestions: Maximum results
            
        Returns:
            List of dicts with 'text', 'doc_type', 'url', 'weight'
        """
        if not prefix or len(prefix) < 2:
            return []
        
        prefix_lower = prefix.lower()
        matches = []
        
        for entry in self.entries:
            text_lower = entry['text'].lower()
            
            # Check if prefix matches start of title or any word in title
            if text_lower.startswith(prefix_lower):
                # Full title starts with prefix — highest boost
                matches.append((entry, entry['weight'] + 50))
            elif any(word.startswith(prefix_lower) 
                     for word in text_lower.split()):
                # A word in the title starts with prefix
                matches.append((entry, entry['weight']))
            elif prefix_lower in text_lower:
                # Substring match — lower priority
                matches.append((entry, entry['weight'] - 20))
        
        # Sort by score descending, then alphabetically
        matches.sort(key=lambda x: (-x[1], x[0]['text'].lower()))
        
        return [m[0] for m in matches[:max_suggestions]]
    
    def build_from_pages(self, pages_dir: Path, verbose: bool = False) -> int:
        """
        Build suggestion index from a pages directory.
        
        Args:
            pages_dir: Path to directory containing page JSON files
            verbose: Print progress
            
        Returns:
            Number of entries indexed
        """
        if not pages_dir.exists():
            return 0
        
        count = 0
        for page_file in sorted(pages_dir.glob('*.json')):
            try:
                with open(page_file) as f:
                    data = json.load(f)
                
                title = data.get('title', '')
                url = data.get('url', '')
                doc_type = data.get('doc_type', 'html')
                headings = data.get('headings', [])
                
                self.add_page(title, url, doc_type, headings)
                count += 1
            except (json.JSONDecodeError, IOError):
                continue
        
        if verbose:
            print(f"Title suggester: {len(self.entries)} entries from {count} pages")
        
        return len(self.entries)
    
    def save(self, path: str, compress: bool = True) -> Path:
        """
        Save suggestion index to disk.
        
        Args:
            path: Base path (without extension)
            compress: Use gzip compression
            
        Returns:
            Path to saved file
        """
        data = {
            'version': 1,
            'entries': self.entries,
        }
        
        if compress:
            out_path = Path(f"{path}.json.gz")
            with gzip.open(out_path, 'wt', encoding='utf-8') as f:
                json.dump(data, f)
        else:
            out_path = Path(f"{path}.json")
            with open(out_path, 'w') as f:
                json.dump(data, f, indent=2)
        
        return out_path
    
    @classmethod
    def load(cls, path: str) -> 'TitleSuggester':
        """
        Load suggestion index from disk.
        
        Args:
            path: Path to the saved file (.json or .json.gz)
            
        Returns:
            TitleSuggester instance
        """
        path = Path(path)
        
        if path.suffix == '.gz':
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                data = json.load(f)
        else:
            with open(path) as f:
                data = json.load(f)
        
        suggester = cls()
        suggester.entries = data.get('entries', [])
        # Rebuild seen set
        suggester._seen = {e['text'].lower() for e in suggester.entries}
        
        return suggester
    
    def get_stats(self) -> Dict:
        """Get stats about the suggestion index."""
        type_counts = {}
        for entry in self.entries:
            dt = entry.get('doc_type', 'unknown')
            type_counts[dt] = type_counts.get(dt, 0) + 1
        
        return {
            'total_entries': len(self.entries),
            'by_type': type_counts,
        }
