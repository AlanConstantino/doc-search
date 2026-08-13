"""Build optional search sidecars (SymSpell / n-gram) from a BM25 index.

These used to be methods on BM25Index. They live here so the index layer
does not import search features. If the index object still implements
``build_symspell`` / ``build_ngram_index`` (tests / older callers), those
are used.
"""

from ...index.store import filter_suggestion_terms
from .symspell import SymSpell
from .ngram import NGramIndex


def build_symspell(index, max_distance: int = 2) -> SymSpell:
    """Build a SymSpell dictionary from an index."""
    method = getattr(index, 'build_symspell', None)
    if callable(method):
        return method(max_distance=max_distance)
    symspell = SymSpell(max_distance=max_distance)
    clean_terms = filter_suggestion_terms(getattr(index, 'doc_freqs', {}) or {})
    for term, doc_freq in clean_terms.items():
        symspell.add_word(term, frequency=doc_freq)
    return symspell


def build_ngram_index(index, n: int = 3) -> NGramIndex:
    """Build an n-gram index from an index."""
    method = getattr(index, 'build_ngram_index', None)
    if callable(method):
        return method(n=n)
    ngram_index = NGramIndex(n=n)
    clean_terms = filter_suggestion_terms(getattr(index, 'doc_freqs', {}) or {})
    for term, doc_freq in clean_terms.items():
        ngram_index.add_term(term, frequency=doc_freq)
    return ngram_index
