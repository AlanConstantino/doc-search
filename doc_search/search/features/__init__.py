"""Optional search features. The core engine imports these; they never import app."""

from .spellcheck import SpellChecker, damerau_levenshtein_distance
from .synonyms import SynonymExpander, QueryExpander, load_synonyms_file, load_default_synonyms
from .ngram import NGramIndex
from .facets import FacetExtractor, FacetIndex
from .suggester import ContentSuggester
from .symspell import SymSpell
from .reranker import Reranker, RerankConfig, RerankMetrics, check_phrase_proximity
from .clicks import ClickLog
from .side_indexes import build_symspell, build_ngram_index

__all__ = [
    'SpellChecker', 'damerau_levenshtein_distance',
    'SynonymExpander', 'QueryExpander', 'load_synonyms_file', 'load_default_synonyms',
    'NGramIndex',
    'FacetExtractor', 'FacetIndex',
    'ContentSuggester',
    'SymSpell',
    'Reranker', 'RerankConfig', 'RerankMetrics', 'check_phrase_proximity',
    'ClickLog',
    'build_symspell', 'build_ngram_index',
]
