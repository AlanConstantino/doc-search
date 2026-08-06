"""
Content-based suggestion engine for search autocomplete.

Extracts high-value terms and multi-word phrases from document body text,
ranked by frequency/importance across the corpus. Unlike the title-based
suggester, this indexes actual content — so users get suggestions for
concepts that appear in documents even if they're not in any page title.

Architecture:
    Index time:
        1. Parse each document's body text
        2. Extract 1-word terms + 2-3 word phrases (configurable)
        3. Filter stop words and junk
        4. Count corpus-wide frequency
        5. Keep top N entries ranked by frequency
        6. Build edge n-gram index for fast lookup

    Query time:
        1. Tokenize user input
        2. Optional fuzzy expansion via SymSpell
        3. Look up candidates via n-gram index
        4. Score candidates against query
        5. Return top N suggestions
"""

import json
import gzip
import re
from collections import defaultdict, Counter
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple


from .utils import STOP_WORDS as _INDEX_STOP_WORDS

# Extra junk filtered from suggestions only (not from BM25 tokenization)
STOP_WORDS = _INDEX_STOP_WORDS | frozenset({
    'let', 'like', 'may', 'much', 'one', 'per', 'say', 'use', 'used', 'using',
    'while', 'whom', 'also', 'because', 'before', 'further', 'having',
    'herself', 'himself', 'itself', 'myself', 'need', 'new', 'ourselves',
    'since', 'still', 'take', 'tell', 'tend', 'themselves', 'upon', 'way',
    'well', 'work', 'yet', 'yourself', 'yourselves', 'get', 'got', 'done',
    'click', 'page', 'next', 'previous', 'see', 'note', 'example',
    'return', 'returns', 'none', 'true', 'false', 'type', 'name',
    'value', 'default', 'set', 'list', 'following', 'given',
    'called', 'make', 'made',
})

# Minimum term length to be a suggestion
_MIN_TERM_LEN = 3

# Minimum corpus frequency to be included
_MIN_FREQUENCY = 2

# Maximum entries to keep in the index
_MAX_ENTRIES = 10000

# Edge n-gram settings
_MIN_NGRAM = 2
_MAX_NGRAM = 10

# Scoring constants
_BONUS_PREFIX_START = 30
_BONUS_WORD_PREFIX = 20
_BONUS_SUBSTRING = 5
_BONUS_ALL_TERMS = 25
_BONUS_EXACT_TERM = 10
_BONUS_EARLY_POSITION = 8
_PENALTY_FUZZY = 5

# Max candidates to score per query
_MAX_CANDIDATES = 500

# Regex for tokenizing text into words
_WORD_RE = re.compile(r'[a-zA-Z][a-zA-Z0-9_]*(?:-[a-zA-Z0-9_]+)*')


class ContentSuggester:
    """
    Indexes terms and phrases from document content for autocomplete.

    Extracts meaningful single words and multi-word phrases from document
    body text, filters stop words, and ranks by corpus-wide frequency.
    Uses edge n-gram indexing for fast candidate lookup at query time.
    """

    def __init__(self, max_words: int = 3):
        """
        Args:
            max_words: Maximum words per phrase (1 = single terms only,
                       2 = up to bigrams, 3 = up to trigrams, etc.)
        """
        self.max_words = max(1, max_words)
        self.entries: List[Dict] = []
        self._ngram_index: Dict[str, Set[int]] = defaultdict(set)
        self._index_dirty: bool = False

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into lowercase words."""
        return [w.lower() for w in _WORD_RE.findall(text) if len(w) >= _MIN_TERM_LEN]

    def _is_valid_term(self, term: str) -> bool:
        """Check if a single term is valid for suggestions."""
        if len(term) < _MIN_TERM_LEN:
            return False
        if term in STOP_WORDS:
            return False
        # Skip pure numbers
        if term.isdigit():
            return False
        # Skip very long terms (likely garbage)
        if len(term) > 40:
            return False
        return True

    def _is_valid_phrase(self, words: List[str]) -> bool:
        """Check if a multi-word phrase is valid for suggestions."""
        # At least one word must not be a stop word
        non_stop = [w for w in words if w not in STOP_WORDS]
        if len(non_stop) < 1:
            return False
        # Phrase shouldn't start or end with a stop word
        if words[0] in STOP_WORDS or words[-1] in STOP_WORDS:
            return False
        # Each word must meet minimum length
        if any(len(w) < 2 for w in words):
            return False
        return True

    def _extract_terms_and_phrases(self, text: str) -> List[str]:
        """Extract valid single terms and multi-word phrases from text."""
        words = self._tokenize(text)
        results = []

        # Single terms
        for w in words:
            if self._is_valid_term(w):
                results.append(w)

        # Multi-word phrases (bigrams, trigrams, etc.)
        for n in range(2, self.max_words + 1):
            for i in range(len(words) - n + 1):
                phrase_words = words[i:i + n]
                if self._is_valid_phrase(phrase_words):
                    results.append(' '.join(phrase_words))

        return results

    def _build_ngram_index(self):
        """Build edge n-gram index from all entries."""
        self._ngram_index = defaultdict(set)
        for idx, entry in enumerate(self.entries):
            for word in entry['words']:
                for n in range(_MIN_NGRAM, min(len(word) + 1, _MAX_NGRAM + 1)):
                    self._ngram_index[word[:n]].add(idx)
                if len(word) > _MAX_NGRAM:
                    self._ngram_index[word].add(idx)
        self._index_dirty = False

    def _ensure_index(self):
        if self._index_dirty or not self._ngram_index:
            self._build_ngram_index()

    def build_from_pages(self, pages_dir: Path, verbose: bool = False) -> int:
        """
        Build suggestion index from page content.

        Args:
            pages_dir: Path to directory containing page JSON files
            verbose: Print progress

        Returns:
            Number of entries indexed
        """
        if not pages_dir.exists():
            return 0

        # Count term/phrase frequencies across all documents
        freq: Counter = Counter()
        doc_count = 0

        for page_file in sorted(pages_dir.glob('*.json')):
            try:
                with open(page_file, encoding='utf-8') as f:
                    data = json.load(f)

                text = data.get('text', '')
                if not text:
                    continue

                # Extract terms and phrases, count unique per doc
                seen_in_doc: set = set()
                for term in self._extract_terms_and_phrases(text):
                    if term not in seen_in_doc:
                        freq[term] += 1
                        seen_in_doc.add(term)

                doc_count += 1
            except (json.JSONDecodeError, IOError):
                continue

        # Filter by minimum frequency and take top entries
        valid = [(term, count) for term, count in freq.items()
                 if count >= _MIN_FREQUENCY]
        valid.sort(key=lambda x: -x[1])
        valid = valid[:_MAX_ENTRIES]

        # Build entries
        self.entries = []
        for term, count in valid:
            words = [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', term)]
            self.entries.append({
                'text': term,
                'frequency': count,
                'words': words,
            })

        # Build n-gram index
        self._build_ngram_index()

        if verbose:
            print(f"Content suggester: {len(self.entries)} entries from {doc_count} pages "
                  f"({len(self._ngram_index)} n-grams)")

        return len(self.entries)

    def _get_candidates(
        self,
        terms: List[str],
        expanded_terms: Optional[Dict[str, List[str]]] = None,
    ) -> Set[int]:
        """Get candidate entry indices matching at least one query term."""
        self._ensure_index()
        candidates: Set[int] = set()

        for term in terms:
            ngram_key = term[:_MAX_NGRAM] if len(term) > _MAX_NGRAM else term
            if ngram_key in self._ngram_index:
                candidates.update(self._ngram_index[ngram_key])

            if expanded_terms and term in expanded_terms:
                for expansion in expanded_terms[term]:
                    exp_key = expansion[:_MAX_NGRAM] if len(expansion) > _MAX_NGRAM else expansion
                    if exp_key in self._ngram_index:
                        candidates.update(self._ngram_index[exp_key])

        return candidates

    def _score_entry(
        self,
        entry: Dict,
        query_terms: List[str],
        expanded_terms: Optional[Dict[str, List[str]]] = None,
    ) -> float:
        """Score an entry against query terms."""
        entry_text_lower = entry['text'].lower()
        entry_words = entry['words']
        freq_boost = min(entry.get('frequency', 1), 100)  # Cap frequency boost

        score = 0.0
        terms_matched = 0

        for q_term in query_terms:
            term_score = self._score_term(q_term, entry_text_lower, entry_words, False)

            if term_score == 0 and expanded_terms and q_term in expanded_terms:
                best_fuzzy = 0.0
                for expansion in expanded_terms[q_term]:
                    fuzzy_score = self._score_term(expansion, entry_text_lower, entry_words, True)
                    best_fuzzy = max(best_fuzzy, fuzzy_score)
                term_score = best_fuzzy

            if term_score > 0:
                terms_matched += 1
            score += term_score

        if terms_matched == 0:
            return 0.0

        if terms_matched == len(query_terms) and len(query_terms) > 1:
            score += _BONUS_ALL_TERMS

        match_ratio = terms_matched / len(query_terms)
        score *= match_ratio

        # Boost by corpus frequency (log scale to avoid domination)
        import math
        score += math.log2(1 + freq_boost) * 5 * match_ratio

        return score

    def _score_term(
        self,
        term: str,
        entry_text_lower: str,
        entry_words: List[str],
        is_fuzzy: bool,
    ) -> float:
        """Score a single query term against an entry."""
        score = 0.0

        if entry_text_lower.startswith(term):
            score += _BONUS_PREFIX_START

        word_matched = False
        for i, word in enumerate(entry_words):
            if word == term:
                score += _BONUS_EXACT_TERM
                if i == 0:
                    score += _BONUS_EARLY_POSITION
                word_matched = True
                break
            elif word.startswith(term):
                score += _BONUS_WORD_PREFIX
                if i == 0:
                    score += _BONUS_EARLY_POSITION
                word_matched = True
                break

        if not word_matched and term in entry_text_lower:
            score += _BONUS_SUBSTRING

        if is_fuzzy and score > 0:
            score -= _PENALTY_FUZZY
            score = max(1.0, score)

        return score

    def suggest(
        self,
        query: str,
        max_suggestions: int = 8,
        symspell=None,
    ) -> List[Dict]:
        """
        Get content-based suggestions for a query.

        Args:
            query: User input (may be partial, multi-word, have typos)
            max_suggestions: Maximum results
            symspell: Optional SymSpell instance for fuzzy expansion

        Returns:
            List of dicts with 'text', 'display_text', 'doc_type', 'url'
        """
        if not query or len(query.strip()) < 2:
            return []

        query_terms = [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', query) if len(w) >= 1]
        if not query_terms:
            return []

        # Fuzzy expand
        expanded_terms: Dict[str, List[str]] = {}
        if symspell:
            for term in query_terms:
                if len(term) >= 2:
                    matches = symspell.lookup(term, max_distance=1, max_results=3)
                    expansions = [word for word, dist, freq in matches if dist > 0]
                    if expansions:
                        expanded_terms[term] = expansions

        # Get candidates
        candidate_indices = self._get_candidates(query_terms, expanded_terms)
        if not candidate_indices:
            return []

        if len(candidate_indices) > _MAX_CANDIDATES:
            candidate_indices = set(sorted(candidate_indices)[:_MAX_CANDIDATES])

        # Score
        scored = []
        for idx in candidate_indices:
            entry = self.entries[idx]
            score = self._score_entry(entry, query_terms, expanded_terms)
            if score > 0:
                scored.append((entry, score))

        scored.sort(key=lambda x: (-x[1], x[0]['text'].lower()))

        results = []
        for entry, _ in scored[:max_suggestions]:
            results.append({
                'text': entry['text'],
                'display_text': entry['text'],
                'doc_type': None,
                'url': None,
            })

        return results

    def save(self, path: str, compress: bool = True) -> Path:
        """Save suggestion index to disk."""
        data = {
            'version': 1,
            'max_words': self.max_words,
            'entries': [
                {'text': e['text'], 'frequency': e.get('frequency', 1)}
                for e in self.entries
            ],
        }

        if compress:
            out_path = Path(f"{path}.json.gz")
            with gzip.open(out_path, 'wt', encoding='utf-8') as f:
                json.dump(data, f)
        else:
            out_path = Path(f"{path}.json")
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

        return out_path

    @classmethod
    def load(cls, path: str) -> 'ContentSuggester':
        """Load suggestion index from disk."""
        path = Path(path)

        if path.suffix == '.gz':
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                data = json.load(f)
        else:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)

        max_words = data.get('max_words', 3)
        suggester = cls(max_words=max_words)
        suggester.entries = []
        for e in data.get('entries', []):
            words = [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', e['text'])]
            suggester.entries.append({
                'text': e['text'],
                'frequency': e.get('frequency', 1),
                'words': words,
            })
        suggester._build_ngram_index()

        return suggester

    def get_stats(self) -> Dict:
        """Get stats about the suggestion index."""
        self._ensure_index()
        single = sum(1 for e in self.entries if ' ' not in e['text'])
        phrases = len(self.entries) - single
        return {
            'total_entries': len(self.entries),
            'single_terms': single,
            'phrases': phrases,
            'ngram_count': len(self._ngram_index),
            'max_words': self.max_words,
        }
