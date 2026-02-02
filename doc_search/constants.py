"""
Constants and configuration values used throughout doc-search.

Extracting magic numbers to a central location improves maintainability
and makes tuning behavior easier.
"""

# =============================================================================
# BM25 Search Parameters
# =============================================================================

# Default BM25 term frequency saturation parameter
# Higher values give more weight to term frequency
DEFAULT_BM25_K1 = 1.5

# Default BM25 length normalization parameter (0-1)
# 0 = no length normalization, 1 = full normalization
DEFAULT_BM25_B = 0.75


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
# Stemmer Cache
# =============================================================================

# Maximum number of stem results to cache
STEM_CACHE_SIZE = 10000


# =============================================================================
# Autocomplete
# =============================================================================

# Default maximum number of autocomplete suggestions
DEFAULT_AUTOCOMPLETE_SUGGESTIONS = 10


# =============================================================================
# Content Weighting (for indexing)
# =============================================================================

# Weight multiplier for title terms during indexing
TITLE_WEIGHT = 3

# Weight multipliers for heading levels (h1=3x, h2=2x, h3+=1x)
def heading_weight(level: int) -> int:
    """Calculate weight multiplier for heading level."""
    return max(1, 4 - level)
