"""Index layer: BM25 inverted index.

Depends on ``core`` and ``extract`` (HTML reparse). Does not import search or app.
"""

from .store import (
    BM25Index,
    find_index_path,
    is_suggestion_worthy,
    filter_suggestion_terms,
    INDEX_FORMAT_VERSION,
)

__all__ = [
    'BM25Index',
    'find_index_path',
    'is_suggestion_worthy',
    'filter_suggestion_terms',
    'INDEX_FORMAT_VERSION',
]
