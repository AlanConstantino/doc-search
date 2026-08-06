"""
Constants and configuration values used throughout doc-search.

Extracting magic numbers to a central location improves maintainability
and makes tuning behavior easier.
"""

# =============================================================================
# Search Result Display
# =============================================================================

# Default snippet length in characters for search results
DEFAULT_SNIPPET_LENGTH = 150

# Maximum snippet length before truncation
MAX_SNIPPET_LENGTH = 200

# Maximum title length before truncation  
MAX_TITLE_LENGTH = 80

# Number of words to consider for snippet window
SNIPPET_WINDOW_WORDS = 20

# Bonus score for phrase match in snippet selection
PHRASE_MATCH_BONUS = 5

# Bonus multiplier for having multiple different query terms
TERM_DIVERSITY_BONUS = 2


# =============================================================================
# Spell Checking
# =============================================================================

# Default maximum edit distance for spelling suggestions
DEFAULT_MAX_EDIT_DISTANCE = 2

# Default number of spelling suggestions to return
DEFAULT_MAX_SUGGESTIONS = 5


# =============================================================================
# Crawler Settings
# =============================================================================

# Default delay between requests to same domain (seconds)
DEFAULT_CRAWL_DELAY = 1.0

# Default request timeout (seconds)
DEFAULT_REQUEST_TIMEOUT = 30.0

# Maximum number of retry attempts for failed URLs
MAX_CRAWL_RETRIES = 3

# Number of pages between state checkpoints
CHECKPOINT_INTERVAL = 100

# Default rate limit backoff time when server returns 429 (seconds)
DEFAULT_RATE_LIMIT_BACKOFF = 60


# =============================================================================
# Content Weighting (for indexing)
# =============================================================================

# =============================================================================
# Reranking Configuration (Two-Stage Retrieval)
# =============================================================================

# Recall stage: fetch this multiple of top_k candidates
RERANK_RECALL_MULTIPLIER = 10

# Maximum candidates to fetch in recall stage
RERANK_MAX_CANDIDATES = 500

# Number of candidates to rerank (balance speed vs quality)
RERANK_CANDIDATE_LIMIT = 100

# Score component weights (must sum to ~1.0)
RERANK_WEIGHT_BM25 = 0.60          # Base BM25 relevance (dominant signal)
RERANK_WEIGHT_FIELD = 0.20         # Field-aware term matching (title > headings > body)
RERANK_WEIGHT_COVERAGE = 0.10      # Query term coverage
RERANK_WEIGHT_PHRASE = 0.10        # Phrase/proximity matches

# Coverage boost strength (beta parameter)
# coverage=1.0 (all terms) → boost = 1 + beta
# coverage=0.5 (half terms) → boost = 1 + 0.5*beta
RERANK_COVERAGE_BETA = 0.4

# Title-specific coverage boost (stronger because title is more important)
RERANK_TITLE_COVERAGE_BETA = 0.6

# Full coverage bonus: extra boost when all query terms are present
RERANK_FULL_COVERAGE_BONUS = 0.2

# Maximum terms to consider for coverage (for very long queries)
RERANK_MAX_COVERAGE_TERMS = 8


# =============================================================================
# Field-Aware Ranking Weights
# =============================================================================

# Field weights for term matching (title > headings > body)
# Based on Elasticsearch/Lucene field boosting recommendations
FIELD_WEIGHT_TITLE = 5.0       # Title matches are 5x more valuable
FIELD_WEIGHT_HEADINGS = 2.5    # Heading matches are 2.5x more valuable  
FIELD_WEIGHT_BODY = 1.0        # Body is the baseline

# Maximum field score (normalized to prevent field domination)
FIELD_MAX_SCORE = 1.0


# =============================================================================
# Phrase Proximity Configuration
# =============================================================================

# Maximum word distance for proximity matching (slop)
PHRASE_MAX_SLOP = 3

# Phrase match boost values
PHRASE_EXACT_MATCH_TITLE = 10.0      # Exact phrase in title
PHRASE_EXACT_MATCH_BODY = 3.0        # Exact phrase in body
PHRASE_PROXIMITY_MATCH_TITLE = 5.0   # Proximity match in title (within slop)
PHRASE_PROXIMITY_MATCH_BODY = 1.5    # Proximity match in body

# =============================================================================
# Term Expansion Weights
# =============================================================================

# Original query terms get full weight
TERM_WEIGHT_ORIGINAL = 1.0

# Synonym expansions
TERM_WEIGHT_SYNONYM = 0.5

# Wildcard/prefix expansions
TERM_WEIGHT_WILDCARD = 0.4

# N-gram substring matches
TERM_WEIGHT_NGRAM = 0.3
