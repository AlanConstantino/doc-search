"""Tokenization and small formatting helpers.

This is the shared analyzer used at both index and query time.
"""

import re


# Common stop words to exclude from indexing.
# These are high-frequency words that appear in almost every document and
# provide little discriminative value for search. Filtering them reduces
# index size and improves search relevance.
#
# Categories:
#   - Articles: a, an, the
#   - Prepositions: at, by, for, from, in, of, on, to, with, etc.
#   - Conjunctions: and, but, or, nor, so, etc.
#   - Pronouns: i, you, he, she, it, we, they, etc.
#   - Auxiliary verbs: am, is, are, was, were, be, been, being, etc.
#   - Modal verbs: can, could, may, might, must, shall, should, will, would
#   - Common adverbs: how, when, where, why, very, just, now, etc.
#   - Quantifiers: all, any, both, each, every, few, more, most, some, etc.
# Minimal English glue words only.
# Programming / docs keywords are intentionally kept so multi-word queries
# like "async with", "yield from", "for loop", "not implemented" stay multi-term
# at both index and query time (same analyzer).
STOP_WORDS = frozenset([
    # articles / demonstratives
    'a', 'an', 'the', 'this', 'that', 'these', 'those',
    # pure pronouns
    'i', 'me', 'my', 'we', 'our', 'you', 'your', 'he', 'him', 'his',
    'she', 'her', 'it', 'its', 'they', 'them', 'their', 'us',
    # copula / auxiliaries that rarely carry docs intent alone
    'am', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing',
    'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can',
    # wh- / discourse glue
    'what', 'when', 'where', 'who', 'which', 'why', 'how',
    'than', 'then', 'so', 'very', 'just', 'also', 'too', 'now',
    'only', 'own', 'same', 'such', 'some', 'any', 'all', 'each',
    'every', 'both', 'few', 'more', 'most', 'other',
    # prepositions that are weak alone in prose (NOT: with/for/from/in/on/to/as/by/at)
    'of', 'about', 'above', 'after', 'again', 'against', 'below',
    'between', 'during', 'into', 'through', 'under', 'until',
    'once', 'there', 'here', 'but',
])
# Kept searchable (critical for multi-word Python/docs queries):
# and, or, not, if, else, for, from, with, as, in, on, to, by, at, is,
# no, nor, up, out, off, over, down




# Code-aware splits: CamelCase, snake_case, dotted identifiers
_CAMEL_1 = re.compile(r'([a-z0-9])([A-Z])')
_CAMEL_2 = re.compile(r'([A-Z]+)([A-Z][a-z])')
_DOTTED_ID = re.compile(r'\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b')

# Letter↔digit boundaries inside identifiers (ticket1234, 64bit, html5)
_LETTER_DIGIT = re.compile(r'([A-Za-z])(\d)')
_DIGIT_LETTER = re.compile(r'(\d)([A-Za-z])')

# Keep structured numeric forms as a single token in addition to parts:
# versions (3.12, 2.6.3), thousands (1,234), hex (0x1234).
_VERSION_RE = re.compile(r'(?<![0-9])\d+(?:\.\d+){1,4}\b')
_COMMA_NUM_RE = re.compile(r'\b\d{1,3}(?:,\d{3})+\b')
_HEX_RE = re.compile(r'\b0[xX][0-9A-Fa-f]+\b')


def _keep_token(token: str) -> bool:
    """True if token is worth indexing / querying."""
    if not token or token in STOP_WORDS:
        return False
    return len(token) > 1 or token.isdigit()


def _split_alnum_parts(token: str) -> list:
    """Split letter/digit runs so ticket1234 → ticket + 1234."""
    if not token:
        return []
    s = _LETTER_DIGIT.sub(r'\1\n\2', token)
    s = _DIGIT_LETTER.sub(r'\1\n\2', s)
    return [p for p in s.split('\n') if p]


def _split_code_token(token: str) -> list:
    """Split a single CamelCase / snake_case / alphanum token into parts (lowercased)."""
    if '_' in token:
        chunks = token.split('_')
    else:
        s = _CAMEL_2.sub(r'\1\n\2', token)
        s = _CAMEL_1.sub(r'\1\n\2', s)
        chunks = s.split('\n')
    out = []
    for chunk in chunks:
        for p in _split_alnum_parts(chunk):
            p = p.lower()
            if _keep_token(p):
                out.append(p)
    return out or ([token.lower()] if token else [])


def _add_token(tokens: list, token: str) -> None:
    if _keep_token(token):
        tokens.append(token)


def _raw_tokens(text: str) -> list:
    """Extract raw lowercase tokens with code-aware splitting (no stemming)."""
    if not text:
        return []

    tokens: list = []

    # Structured numeric forms first (before dotted-id rewrite eats the dots).
    # Lookbehind on versions lets v2.6.3 / python3.12 yield the version as one token.
    for m in _HEX_RE.finditer(text):
        whole = m.group(0).lower()
        _add_token(tokens, whole)
        payload = whole[2:]
        if len(payload) >= 2:
            _add_token(tokens, payload)
    for m in _VERSION_RE.finditer(text):
        _add_token(tokens, m.group(0))
    for m in _COMMA_NUM_RE.finditer(text):
        _add_token(tokens, m.group(0).replace(',', ''))

    # Dotted identifiers → spaces (os.path.join → os path join)
    expanded = _DOTTED_ID.sub(lambda m: m.group(0).replace('.', ' '), text)
    for m in re.finditer(r'\b[A-Za-z][A-Za-z0-9_]*\b|\b\d+[A-Za-z][A-Za-z0-9_]*\b|\b\d+\b', expanded):
        raw = m.group(0)
        # Whole hex already emitted (0x1234 + payload); skip 0x… fragments.
        if raw.lower().startswith('0x'):
            continue
        if raw.isdigit():
            _add_token(tokens, raw)
            continue
        mixed = (
            any(c.isupper() for c in raw[1:])
            or '_' in raw
            or any(c.isdigit() for c in raw)
        )
        if mixed:
            for part in _split_code_token(raw):
                _add_token(tokens, part)
            full = raw.lower()
            # Keep full form for CamelCase / snake_case / alphanum (3d, html5)
            if len(full) > 2 or (len(full) >= 2 and any(c.isdigit() for c in full)):
                _add_token(tokens, full)
        else:
            _add_token(tokens, raw.lower())
    return tokens


def _looks_numeric(token: str) -> bool:
    """True for digits, versions, hex, or other tokens Porter stemming would mangle."""
    if not token:
        return False
    if token[0].isdigit() or token.startswith('0x'):
        return True
    return any(c.isdigit() for c in token) and not token.isalpha()


def _maybe_stem(token: str, stem_fn) -> str:
    if _looks_numeric(token):
        return token
    return stem_fn(token)


# Literal phrase tokens: keep stopwords and the surface form (no CamelCase split).
_PHRASE_TOKEN_RE = re.compile(
    r'0[xX][0-9A-Fa-f]+'
    r'|\d+(?:\.\d+)+'
    r'|\d+[A-Za-z][A-Za-z0-9_]*'
    r'|[A-Za-z][A-Za-z0-9_]*'
    r'|\d+'
)


def tokenize_phrase(text: str) -> list:
    """Tokenize a quoted / exact-match phrase as the user typed it.

    Unlike ``tokenize()``, this keeps stopwords, 1-character words, and
    CamelCase identifiers intact, and never stems. That way
    ``"list of lists"`` and ``"HTTPResponse"`` can match literally.
    """
    if not text:
        return []
    return [m.group(0).lower() for m in _PHRASE_TOKEN_RE.finditer(text)]


def tokenize(text: str, apply_stemming: bool = False) -> list:
    """
    Tokenize text into lowercase words for indexing and search.

    Code-aware: splits CamelCase, snake_case, dotted.ids, and glued
    alphanumerics (ticket1234 → ticket + 1234). Keeps versions (3.12),
    hex (0x1234), and digit-leading tokens (3d, 7zip).
    Optional Porter stemming when apply_stemming=True (skipped for numeric tokens).
    """
    tokens = _raw_tokens(text)
    if apply_stemming:
        from .stemmer import stem
        tokens = [_maybe_stem(t, stem) for t in tokens]
    return tokens


def tokenize_with_exact(text: str, apply_stemming: bool = True):
    """
    Return (stemmed_tokens, exact_tokens).

    Stemmed forms power recall; exact (unstemmed) forms power match bonus.
    Numeric / version / hex tokens are never stemmed.
    """
    exact = _raw_tokens(text)
    if not apply_stemming:
        return list(exact), list(exact)
    from .stemmer import stem
    stemmed = [_maybe_stem(t, stem) for t in exact]
    return stemmed, exact


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"

