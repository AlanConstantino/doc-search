"""
Search index building with BM25 scoring.

Supports fielded BM25, bigram phrases, doc priors, section chunks,
binary (pickle) persistence, array-backed postings, and precomputed IDF.
"""

import array
import hashlib
import heapq
import json
import gzip
import math
import mmap
import os
import pickle
import re
import struct
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Iterable
from urllib.parse import urlparse

from .utils import tokenize, tokenize_with_exact
from .symspell import SymSpell
from .ngram import NGramIndex

# Regex: valid suggestion terms
_VALID_TERM_RE = re.compile(r'^[a-z][a-z0-9\-]{1,24}$')
_HEX_LIKE_RE = re.compile(r'^[0-9a-f]{8,}$')
_ID_LIKE_RE = re.compile(r'^[a-z]\d{3,}')

# Field weights for fielded BM25 (title > headings > body)
FIELD_WEIGHT_TITLE = 5.0
FIELD_WEIGHT_HEADINGS = 2.5
FIELD_WEIGHT_BODY = 1.0

# Exact (unstemmed) match bonus applied on top of stemmed BM25
EXACT_MATCH_BONUS = 0.15

# Doc prior weights
PRIOR_WEIGHT = 0.08
PREVIEW_CHARS = 600
INDEX_FORMAT_VERSION = 3

# mmap postings magic
_POSTINGS_MAGIC = b'DSIDX003'
_POSTINGS_HEADER = struct.Struct('<8sI')  # magic, num_terms
_TERM_ENTRY = struct.Struct('<IHII')  # term_len, reserved, offset, count  — term bytes follow padded


def is_suggestion_worthy(term: str) -> bool:
    """Check if a term is clean enough for autocomplete/spellcheck suggestions."""
    if not _VALID_TERM_RE.match(term):
        return False
    if _HEX_LIKE_RE.match(term):
        return False
    if _ID_LIKE_RE.match(term):
        return False
    if term.endswith('-'):
        return False
    digit_count = sum(1 for c in term if c.isdigit())
    if digit_count > 0:
        letter_count = sum(1 for c in term if c.isalpha())
        if letter_count < digit_count * 3:
            return False
    if len(term) >= 5 and not re.search(r'[aeiouy]', term):
        return False
    return True


def filter_suggestion_terms(doc_freqs: dict) -> dict:
    """Filter doc_freqs to only include suggestion-worthy terms."""
    return {term: freq for term, freq in doc_freqs.items()
            if is_suggestion_worthy(term)}


def find_index_path(site_dir: Path) -> Optional[Path]:
    """Locate an index file in a site directory (binary preferred)."""
    site_dir = Path(site_dir)
    for name in ('index.pkl.gz', 'index.json.gz', 'index.json', 'index.pkl'):
        p = site_dir / name
        if p.exists():
            return p
    return None


def _slugify(text: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return s[:60] or 'section'


def _url_depth(url: str) -> int:
    try:
        path = urlparse(url).path or '/'
        return max(0, len([p for p in path.split('/') if p]))
    except Exception:
        return 0


def _doc_type_prior(doc_type: str) -> float:
    # Prefer real docs slightly over raw HTML shells
    return {
        'pdf': 0.05,
        'docx': 0.04,
        'xlsx': 0.02,
        'pptx': 0.03,
        'html': 0.0,
    }.get(doc_type or 'html', 0.0)


class _Postings:
    """Parallel array postings: doc_ids + term freqs (and optional field tfs)."""

    __slots__ = ('docs', 'tfs', 'title_tfs', 'head_tfs')

    def __init__(self):
        self.docs = array.array('I')       # doc ids
        self.tfs = array.array('H')        # combined/body-ish tf (capped)
        self.title_tfs = array.array('H')  # title field tf
        self.head_tfs = array.array('H')   # heading field tf

    def append(self, doc_id: int, tf: int, title_tf: int = 0, head_tf: int = 0):
        self.docs.append(doc_id & 0xFFFFFFFF)
        self.tfs.append(min(tf, 65535))
        self.title_tfs.append(min(title_tf, 65535))
        self.head_tfs.append(min(head_tf, 65535))

    def __len__(self):
        return len(self.docs)

    def iter_rows(self) -> Iterable[Tuple[int, int, int, int]]:
        for i in range(len(self.docs)):
            yield self.docs[i], self.tfs[i], self.title_tfs[i], self.head_tfs[i]

    def without_doc(self, doc_id: int) -> '_Postings':
        out = _Postings()
        for d, tf, tt, ht in self.iter_rows():
            if d != doc_id:
                out.append(d, tf, tt, ht)
        return out

    def to_legacy_list(self) -> List[tuple]:
        return [(int(d), int(tf)) for d, tf, _, _ in self.iter_rows()]

    @classmethod
    def from_legacy(cls, pairs) -> '_Postings':
        p = cls()
        for item in pairs:
            if len(item) >= 4:
                p.append(int(item[0]), int(item[1]), int(item[2]), int(item[3]))
            else:
                p.append(int(item[0]), int(item[1]), 0, 0)
        return p


class BM25Index:
    """
    BM25-based inverted index for document search.

    Features:
        - Fielded BM25 (title / headings / body)
        - Bigram postings for phrase recall
        - Static document priors
        - Section/anchor chunk docs
        - Precomputed IDF + heap top-k
        - array.array postings + binary pickle/mmap save
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75, stem: bool = True):
        if k1 < 0:
            raise ValueError(f"k1 must be non-negative, got {k1}")
        if not (0 <= b <= 1):
            raise ValueError(f"b must be between 0 and 1, got {b}")

        self.k1 = k1
        self.b = b
        self.stem = stem

        self.documents: Dict[int, Dict[str, Any]] = {}
        self.url_to_id: Dict[str, int] = {}

        # term -> _Postings
        self.index: Dict[str, _Postings] = {}
        # bigram "a b" -> _Postings (body co-occurrence)
        self.bigrams: Dict[str, _Postings] = {}

        self.doc_lengths: Dict[int, int] = {}
        self.avg_doc_length: float = 0.0
        self.total_docs: int = 0
        self.doc_freqs: Dict[str, int] = defaultdict(int)

        self.content_hashes: Dict[str, str] = {}
        self._content_hashes: set = set()

        # Precomputed IDF cache (rebuilt on load / after build)
        self._idf_cache: Dict[str, float] = {}

        # CTR boosts: url -> clicks (optional, loaded externally)
        self.click_counts: Dict[str, int] = {}

        # Chunk docs use high IDs so they never collide with caller-assigned ids
        self._chunk_id_seq = 1_000_000_000

        # mmap state (optional)
        self._mmap: Optional[mmap.mmap] = None
        self._mmap_path: Optional[Path] = None
        self._mmap_term_dir: Dict[str, Tuple[int, int]] = {}  # term -> (offset, count)

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def _add_posting(self, store: Dict[str, _Postings], term: str,
                     doc_id: int, tf: int, title_tf: int = 0, head_tf: int = 0):
        p = store.get(term)
        if p is None:
            p = _Postings()
            store[term] = p
        p.append(doc_id, tf, title_tf, head_tf)

    def add_document(self, doc_id: int, url: str, title: str, text: str,
                     description: str = '', headings: List[tuple] = None,
                     doc_type: str = 'html', *,
                     inbound_links: int = 0,
                     is_chunk: bool = False,
                     parent_url: str = '',
                     index_chunks: bool = True):
        """Add a document to the index."""
        # Replace existing id cleanly (avoids stale postings on overwrite)
        if doc_id in self.documents:
            self.remove_document(doc_id)

        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        if not is_chunk:
            if text_hash in self._content_hashes:
                return
            self._content_hashes.add(text_hash)

        headings = headings or []
        headings_text = ' '.join(h for _, h in headings) if headings else ''

        # Tokenize fields (stem for recall + keep exact forms)
        title_stem, title_exact = tokenize_with_exact(title, apply_stemming=self.stem)
        head_stem, head_exact = tokenize_with_exact(headings_text, apply_stemming=self.stem)
        body_stem, body_exact = tokenize_with_exact(text, apply_stemming=self.stem)

        # Field term freqs (stemmed)
        def _tf(tokens: List[str]) -> Dict[str, int]:
            d: Dict[str, int] = defaultdict(int)
            for t in tokens:
                d[t] += 1
            return d

        title_tf = _tf(title_stem)
        head_tf = _tf(head_stem)
        body_tf = _tf(body_stem)

        # Combined length (weighted like classic BM25 length)
        all_len = len(title_stem) * 3 + len(head_stem) * 2 + len(body_stem)
        if all_len == 0:
            all_len = 1

        # Exact forms for bonus
        exact_set = set(title_exact) | set(head_exact) | set(body_exact)

        # Static prior
        length_prior = min(1.0, math.log1p(all_len) / 10.0)  # longer-ish docs
        depth = _url_depth(url)
        depth_prior = max(0.0, 0.15 - 0.03 * depth)  # prefer shallower paths
        type_prior = _doc_type_prior(doc_type)
        in_prior = min(0.2, 0.02 * math.log1p(inbound_links))
        chunk_penalty = -0.03 if is_chunk else 0.0
        prior = length_prior * 0.3 + depth_prior + type_prior + in_prior + chunk_penalty

        preview = (text or '')[:PREVIEW_CHARS]
        if description and len(preview) < 80:
            preview = (description + ' ' + preview)[:PREVIEW_CHARS]

        self.documents[doc_id] = {
            'url': url,
            'title': title,
            'description': description,
            'doc_type': doc_type,
            'headings_text': headings_text,
            'preview': preview,
            'prior': round(prior, 4),
            'exact_terms': exact_set if len(exact_set) < 5000 else set(list(exact_set)[:5000]),
            'is_chunk': is_chunk,
            'parent_url': parent_url or '',
            'inbound_links': inbound_links,
        }
        self.url_to_id[url] = doc_id
        self.doc_lengths[doc_id] = all_len

        # Merge field tfs into postings
        terms = set(title_tf) | set(head_tf) | set(body_tf)
        for term in terms:
            tt = title_tf.get(term, 0)
            ht = head_tf.get(term, 0)
            bt = body_tf.get(term, 0)
            # Combined tf used as body-ish baseline (title/head also counted lightly)
            combined = bt + tt * 3 + ht * 2
            self._add_posting(self.index, term, doc_id, combined, tt, ht)
            self.doc_freqs[term] += 1

        # Bigrams from body (stemmed) for phrase recall
        if len(body_stem) >= 2:
            bg_tf: Dict[str, int] = defaultdict(int)
            for a, b in zip(body_stem, body_stem[1:]):
                bg_tf[f'{a} {b}'] += 1
            # Also title bigrams
            for a, b in zip(title_stem, title_stem[1:]):
                bg_tf[f'{a} {b}'] += 2
            for bg, freq in bg_tf.items():
                self._add_posting(self.bigrams, bg, doc_id, freq)

        self.total_docs += 1
        self._update_avg_doc_length()

        # Section/anchor chunks from headings
        if index_chunks and not is_chunk and headings and text:
            self._add_section_chunks(doc_id, url, title, text, headings, doc_type)

    def _add_section_chunks(self, parent_id: int, url: str, title: str,
                            text: str, headings: List[tuple], doc_type: str):
        """Index heading sections as url#anchor chunk documents."""
        # Cap chunks per page
        max_chunks = 20
        count = 0
        lower_text = text
        for level, heading in headings:
            if count >= max_chunks:
                break
            if not heading or len(heading) < 2:
                continue
            pos = lower_text.find(heading)
            if pos < 0:
                # try case-insensitive
                pos = lower_text.lower().find(heading.lower())
            if pos < 0:
                chunk_body = heading
            else:
                chunk_body = text[pos:pos + 2500]
            slug = _slugify(heading)
            chunk_url = f'{url}#{slug}'
            if chunk_url in self.url_to_id:
                continue
            next_id = self._chunk_id_seq
            self._chunk_id_seq += 1
            self.add_document(
                doc_id=next_id,
                url=chunk_url,
                title=f'{title} › {heading}' if title else heading,
                text=chunk_body,
                description=heading,
                headings=[(level, heading)],
                doc_type=doc_type,
                is_chunk=True,
                parent_url=url,
                index_chunks=False,
            )
            count += 1

    def _update_avg_doc_length(self):
        if self.doc_lengths:
            self.avg_doc_length = sum(self.doc_lengths.values()) / len(self.doc_lengths)
        else:
            self.avg_doc_length = 1.0

    def rebuild_idf_cache(self):
        """Precompute IDF for every term."""
        n = self.total_docs
        cache = {}
        for term, df in self.doc_freqs.items():
            if df <= 0:
                cache[term] = 0.0
            else:
                cache[term] = math.log((n - df + 0.5) / (df + 0.5) + 1)
        self._idf_cache = cache

    def _idf(self, term: str) -> float:
        if self._idf_cache:
            return self._idf_cache.get(term, 0.0)
        n = self.total_docs
        df = self.doc_freqs.get(term, 0)
        if df == 0:
            return 0.0
        return math.log((n - df + 0.5) / (df + 0.5) + 1)

    # ------------------------------------------------------------------
    # Build from pages
    # ------------------------------------------------------------------

    def build_from_pages(self, pages_dir: Path, verbose: bool = True, parser: str = 'dom') -> int:
        pages_dir = Path(pages_dir)
        page_files = list(pages_dir.glob('*.json'))
        total_files = len(page_files)

        if verbose:
            print(f"Indexing {total_files} pages (parser: {parser})...")

        from .parser import extract_text, extract_links
        from .dom import extract_text_dom

        # Pass 1: load pages + inbound link counts
        pages = []
        inbound: Dict[str, int] = defaultdict(int)
        reparsed_count = 0

        for page_file in page_files:
            try:
                with open(page_file, 'r', encoding='utf-8') as f:
                    page = json.load(f)
            except (json.JSONDecodeError, IOError, KeyError):
                continue

            if 'raw_html' in page and page['raw_html']:
                if parser == 'dom':
                    extracted = extract_text_dom(page['raw_html'])
                else:
                    extracted = extract_text(page['raw_html'])
                page['text'] = extracted.get('text', '')
                page['title'] = extracted.get('title', page.get('title', ''))
                page['description'] = extracted.get('description', page.get('description', ''))
                page['headings'] = extracted.get('headings', page.get('headings', []))
                try:
                    for link in extract_links(page['raw_html'], page.get('url', '')):
                        inbound[link] += 1
                except Exception:
                    pass
                reparsed_count += 1

            if not page.get('text', '').strip():
                continue
            pages.append(page)

        doc_id = 0
        for i, page in enumerate(pages):
            url = page['url']
            self.add_document(
                doc_id=doc_id,
                url=url,
                title=page.get('title', ''),
                text=page.get('text', ''),
                description=page.get('description', ''),
                headings=page.get('headings', []),
                doc_type=page.get('doc_type', 'html'),
                inbound_links=inbound.get(url, 0),
            )
            hash_page = {
                'title': page.get('title', ''),
                'text': page.get('text', ''),
                'description': page.get('description', ''),
                'headings': page.get('headings', []),
            }
            self.content_hashes[url] = self._compute_content_hash(hash_page)
            doc_id = max(self.documents.keys(), default=doc_id) + 1

            if verbose and (i + 1) % 500 == 0:
                print(f"  Indexed {i + 1}/{len(pages)} pages...")

        self.rebuild_idf_cache()

        if verbose:
            print("Indexing complete!")
            print(f"  Documents: {self.total_docs}")
            print(f"  Unique terms: {len(self.index)}")
            print(f"  Bigrams: {len(self.bigrams)}")
            print(f"  Avg document length: {self.avg_doc_length:.1f} terms")
            if reparsed_count:
                print(f"  Re-parsed from raw HTML: {reparsed_count}")

        return self.total_docs

    def remove_document(self, doc_id: int):
        if doc_id not in self.documents:
            return

        url = self.documents[doc_id]['url']

        # Also remove child chunks
        child_ids = [
            did for did, d in self.documents.items()
            if d.get('parent_url') == url and d.get('is_chunk')
        ]
        for cid in child_ids:
            if cid != doc_id:
                self.remove_document(cid)

        terms_to_remove = []
        for term, postings in list(self.index.items()):
            new_p = postings.without_doc(doc_id)
            if len(new_p) < len(postings):
                self.doc_freqs[term] -= 1
                if self.doc_freqs[term] <= 0 or len(new_p) == 0:
                    terms_to_remove.append(term)
                else:
                    self.index[term] = new_p
        for term in terms_to_remove:
            self.index.pop(term, None)
            self.doc_freqs.pop(term, None)

        bg_remove = []
        for bg, postings in list(self.bigrams.items()):
            new_p = postings.without_doc(doc_id)
            if len(new_p) == 0:
                bg_remove.append(bg)
            elif len(new_p) < len(postings):
                self.bigrams[bg] = new_p
        for bg in bg_remove:
            del self.bigrams[bg]

        del self.documents[doc_id]
        self.url_to_id.pop(url, None)
        self.doc_lengths.pop(doc_id, None)
        self.content_hashes.pop(url, None)

        self.total_docs = max(0, self.total_docs - 1)
        self._update_avg_doc_length()
        self._idf_cache.clear()

    @staticmethod
    def _compute_content_hash(page: dict) -> str:
        content = json.dumps({
            'title': page.get('title', ''),
            'text': page.get('text', ''),
            'description': page.get('description', ''),
            'headings': page.get('headings', []),
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def build_from_pages_incremental(self, pages_dir: Path, verbose: bool = True,
                                     parser: str = 'dom') -> dict:
        from .parser import extract_text
        from .dom import extract_text_dom

        pages_dir = Path(pages_dir)
        page_files = list(pages_dir.glob('*.json'))

        if verbose:
            print(f"Incremental indexing from {len(page_files)} page files (parser: {parser})...")

        current_pages = {}
        for page_file in page_files:
            try:
                with open(page_file, 'r', encoding='utf-8') as f:
                    page = json.load(f)
                if 'raw_html' in page and page['raw_html']:
                    if parser == 'dom':
                        extracted = extract_text_dom(page['raw_html'])
                    else:
                        extracted = extract_text(page['raw_html'])
                    page['text'] = extracted.get('text', '')
                    page['title'] = extracted.get('title', page.get('title', ''))
                    page['description'] = extracted.get('description', page.get('description', ''))
                    page['headings'] = extracted.get('headings', page.get('headings', []))
                if not page.get('text', '').strip():
                    continue
                current_pages[page['url']] = page
            except (json.JSONDecodeError, IOError, KeyError):
                continue

        current_urls = set(current_pages.keys())
        indexed_urls = set(self.content_hashes.keys())

        new_urls = current_urls - indexed_urls
        removed_urls = indexed_urls - current_urls
        possibly_changed = current_urls & indexed_urls

        updated_urls = set()
        unchanged_urls = set()
        for url in possibly_changed:
            page = current_pages[url]
            new_hash = self._compute_content_hash(page)
            if new_hash != self.content_hashes.get(url):
                updated_urls.add(url)
            else:
                unchanged_urls.add(url)

        for url in removed_urls | updated_urls:
            doc_id = self.url_to_id.get(url)
            if doc_id is not None:
                self.remove_document(doc_id)

        next_doc_id = max(self.documents.keys()) + 1 if self.documents else 0
        for url in sorted(new_urls | updated_urls):
            page = current_pages[url]
            self.add_document(
                doc_id=next_doc_id,
                url=page['url'],
                title=page.get('title', ''),
                text=page.get('text', ''),
                description=page.get('description', ''),
                headings=page.get('headings', []),
                doc_type=page.get('doc_type', 'html'),
            )
            self.content_hashes[url] = self._compute_content_hash(page)
            next_doc_id = max(self.documents.keys(), default=next_doc_id) + 1

        self.rebuild_idf_cache()

        stats = {
            'new': len(new_urls),
            'updated': len(updated_urls),
            'removed': len(removed_urls),
            'unchanged': len(unchanged_urls),
        }
        if verbose:
            print("Incremental indexing complete!")
            print(f"  {stats['new']} new, {stats['updated']} updated, "
                  f"{stats['removed']} removed, {stats['unchanged']} unchanged")
            print(f"  Total documents: {self.total_docs}")
            print(f"  Unique terms: {len(self.index)}")
        return stats

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _bm25_tf(self, tf: float, doc_length: int, avg_dl: float,
                 k1: float, b: float) -> float:
        return (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_length / avg_dl))

    def _posting_rows(self, term: str):
        """Yield (doc_id, tf, title_tf, head_tf) from memory or mmap."""
        # Prefer in-memory index (always complete, includes incremental updates)
        postings = self.index.get(term)
        if postings is not None:
            return postings.iter_rows()
        # Fallback: mmap sidecar (cold path / external tools)
        mm = self._mmap
        if mm is None:
            return ()
        ent = self._mmap_term_dir.get(term)
        if not ent:
            return ()
        offset, count = ent
        rows = []
        for i in range(count):
            doc_id, tf, tt, ht, _pad = struct.unpack_from('<IHHHH', mm, offset + i * 12)
            rows.append((doc_id, tf, tt, ht))
        return rows

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search using fielded BM25 + bigrams + priors + exact bonus + CTR."""
        # Tokenize with exact forms for bonus
        stem_terms, exact_terms = tokenize_with_exact(query, apply_stemming=self.stem)
        if not stem_terms and not exact_terms:
            # fallback
            stem_terms = tokenize(query, apply_stemming=self.stem)
            exact_terms = tokenize(query, apply_stemming=False)

        if not stem_terms:
            return []

        scores: Dict[int, float] = defaultdict(float)
        avg_dl = self.avg_doc_length if self.avg_doc_length > 0 else 1.0
        k1, b = self.k1, self.b
        doc_lengths = self.doc_lengths
        w_title, w_head, w_body = FIELD_WEIGHT_TITLE, FIELD_WEIGHT_HEADINGS, FIELD_WEIGHT_BODY
        w_sum = w_title + w_head + w_body

        # Fielded BM25 over stemmed terms (mmap postings when available)
        for term in stem_terms:
            idf = self._idf(term)
            if idf == 0:
                continue
            rows = self._posting_rows(term)
            if not rows:
                continue
            for doc_id, tf, title_tf, head_tf in rows:
                doc_length = doc_lengths.get(doc_id, avg_dl)
                body_tf = max(0, tf - title_tf * 3 - head_tf * 2)
                field_score = (
                    w_title * self._bm25_tf(title_tf, doc_length, avg_dl, k1, b) +
                    w_head * self._bm25_tf(head_tf, doc_length, avg_dl, k1, b) +
                    w_body * self._bm25_tf(body_tf + title_tf + head_tf, doc_length, avg_dl, k1, b)
                ) / w_sum
                scores[doc_id] += idf * field_score

        # Bigram boost for adjacent query terms
        if len(stem_terms) >= 2:
            for a, btm in zip(stem_terms, stem_terms[1:]):
                bg = f'{a} {btm}'
                postings = self.bigrams.get(bg)
                if not postings:
                    continue
                # fixed boost scaled by rarity
                idf_bg = self._idf(a) * 0.5
                for doc_id, tf, _, _ in postings.iter_rows():
                    scores[doc_id] += idf_bg * min(tf, 5) * 0.35

        if not scores:
            return []

        # Exact match bonus + prior + CTR
        exact_set = set(exact_terms)
        for doc_id in list(scores.keys()):
            doc = self.documents.get(doc_id)
            if not doc:
                continue
            if exact_set and doc.get('exact_terms'):
                hits = len(exact_set & doc['exact_terms'])
                if hits:
                    scores[doc_id] *= (1.0 + EXACT_MATCH_BONUS * hits / max(1, len(exact_set)))
            scores[doc_id] += PRIOR_WEIGHT * float(doc.get('prior', 0.0))
            # CTR
            clicks = self.click_counts.get(doc.get('url', ''), 0)
            if clicks:
                scores[doc_id] += 0.05 * math.log1p(clicks)

        # heapq top-k (faster than full sort)
        top = heapq.nlargest(top_k, scores.items(), key=lambda x: x[1])

        results = []
        for doc_id, score in top:
            doc = self.documents[doc_id]
            results.append({
                'url': doc['url'],
                'title': doc['title'],
                'description': doc['description'],
                'score': round(score, 4),
                'doc_type': doc.get('doc_type', 'html'),
                'preview': doc.get('preview', ''),
                'headings_text': doc.get('headings_text', ''),
                'is_chunk': doc.get('is_chunk', False),
            })
        return results

    def has_phrase_bigrams(self, phrase_words: List[str], doc_url: str) -> bool:
        """True if all adjacent bigrams of phrase appear in the doc."""
        if len(phrase_words) < 2:
            return True
        doc_id = self.url_to_id.get(doc_url)
        if doc_id is None:
            return False
        stems = tokenize(' '.join(phrase_words), apply_stemming=self.stem)
        if len(stems) < 2:
            return True
        for a, b in zip(stems, stems[1:]):
            postings = self.bigrams.get(f'{a} {b}')
            if not postings:
                return False
            if doc_id not in postings.docs:
                # array membership
                found = False
                for d in postings.docs:
                    if d == doc_id:
                        found = True
                        break
                if not found:
                    return False
        return True

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _serialize_state(self) -> dict:
        # Convert postings to compact tuples for pickle
        index_data = {}
        for term, p in self.index.items():
            index_data[term] = list(p.iter_rows())
        bigram_data = {}
        for bg, p in self.bigrams.items():
            bigram_data[bg] = list(p.iter_rows())

        # exact_terms as list for JSON/pickle
        docs = {}
        for did, d in self.documents.items():
            dd = dict(d)
            et = dd.get('exact_terms')
            if isinstance(et, set):
                dd['exact_terms'] = list(et)
            docs[did] = dd

        return {
            'format_version': INDEX_FORMAT_VERSION,
            'k1': self.k1,
            'b': self.b,
            'stem': self.stem,
            'documents': docs,
            'url_to_id': self.url_to_id,
            'index': index_data,
            'bigrams': bigram_data,
            'doc_lengths': self.doc_lengths,
            'avg_doc_length': self.avg_doc_length,
            'total_docs': self.total_docs,
            'doc_freqs': dict(self.doc_freqs),
            'content_hashes': self.content_hashes,
            '_content_hashes': list(self._content_hashes),
            'click_counts': self.click_counts,
            'idf_cache': self._idf_cache,
        }

    def _restore_state(self, data: dict):
        self.k1 = data['k1']
        self.b = data['b']
        self.stem = data.get('stem', True)

        docs_in = data['documents']
        self.documents = {}
        for k, v in docs_in.items():
            did = int(k)
            dd = dict(v)
            et = dd.get('exact_terms')
            if isinstance(et, list):
                dd['exact_terms'] = set(et)
            elif et is None:
                dd['exact_terms'] = set()
            # ensure preview key
            dd.setdefault('preview', dd.get('description', '')[:PREVIEW_CHARS])
            dd.setdefault('headings_text', '')
            dd.setdefault('prior', 0.0)
            self.documents[did] = dd

        self.url_to_id = {str(u): int(i) for u, i in data['url_to_id'].items()}

        self.index = {}
        for term, rows in data.get('index', {}).items():
            self.index[term] = _Postings.from_legacy(rows)

        self.bigrams = {}
        for bg, rows in data.get('bigrams', {}).items():
            self.bigrams[bg] = _Postings.from_legacy(rows)

        dl = data.get('doc_lengths', {})
        self.doc_lengths = {int(k): v for k, v in dl.items()}
        self.avg_doc_length = data.get('avg_doc_length', 1.0)
        self.total_docs = data.get('total_docs', len(self.documents))
        self.doc_freqs = defaultdict(int, data.get('doc_freqs', {}))
        self.content_hashes = data.get('content_hashes', {})
        self._content_hashes = set(data.get('_content_hashes', []))
        self.click_counts = data.get('click_counts', {})
        self._idf_cache = data.get('idf_cache') or {}
        if not self._idf_cache:
            self.rebuild_idf_cache()
        # Keep chunk ids out of the way of future caller-assigned ids
        max_id = max(self.documents.keys()) if self.documents else 0
        self._chunk_id_seq = max(1_000_000_000, max_id + 1)

    def save(self, filepath: Path, compress: bool = True):
        """
        Save index to disk.

        Default: binary pickle+gzip (.pkl.gz) for fast load.
        Also writes optional mmap postings sidecar (.postings).
        JSON.gz still supported if filepath ends with .json/.json.gz.
        """
        filepath = Path(filepath)
        if not self._idf_cache:
            self.rebuild_idf_cache()

        state = self._serialize_state()

        # Prefer binary unless caller asked for json explicitly
        suffix = ''.join(filepath.suffixes)
        want_json = suffix.endswith('.json') or suffix.endswith('.json.gz')

        if want_json:
            # Legacy JSON path (convert keys)
            json_state = dict(state)
            json_state['documents'] = {str(k): v for k, v in state['documents'].items()}
            json_state['doc_lengths'] = {str(k): v for k, v in state['doc_lengths'].items()}
            # sets already lists
            raw = json.dumps(json_state)
            if compress or suffix.endswith('.gz'):
                out = filepath if str(filepath).endswith('.gz') else filepath.with_suffix(filepath.suffix + '.gz')
                if not str(out).endswith('.json.gz'):
                    out = filepath.with_suffix('.json.gz')
                with gzip.open(out, 'wt', encoding='utf-8') as f:
                    f.write(raw)
                return out
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(raw)
            return filepath

        # Binary pickle
        out = filepath
        if out.suffix == '.gz' and not str(out).endswith('.pkl.gz'):
            out = out.with_name(out.name.replace('.json.gz', '.pkl.gz'))
        if not str(out).endswith('.pkl.gz'):
            # replace .json etc
            stem = out.name
            for s in ('.json.gz', '.json', '.pkl', '.gz'):
                if stem.endswith(s):
                    stem = stem[: -len(s)]
                    break
            out = out.with_name(stem + '.pkl.gz')

        with gzip.open(out, 'wb') as f:
            pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)

        # mmap postings sidecar
        try:
            self._write_mmap_postings(out.with_suffix('').with_suffix('.postings'))
        except Exception:
            pass

        return out

    def _write_mmap_postings(self, path: Path):
        """Write term directory + postings blob for mmap loading."""
        # Layout: header | term_dir_blob | postings_blob
        # term_dir: repeated (term_len u16, pad u16, offset u32, count u32, term bytes padded to 4)
        terms = sorted(self.index.keys())
        dir_parts = []
        postings_blob = bytearray()
        offset = 0
        for term in terms:
            p = self.index[term]
            count = len(p)
            tb = term.encode('utf-8')
            pad = (4 - (len(tb) % 4)) % 4
            dir_parts.append(struct.pack('<HHII', len(tb), pad, offset, count) + tb + b'\x00' * pad)
            # each posting: doc u32, tf u16, title u16, head u16, pad u16 = 12 bytes
            for doc_id, tf, tt, ht in p.iter_rows():
                postings_blob.extend(struct.pack('<IHHHH', doc_id, tf, tt, ht, 0))
            offset += count * 12

        dir_blob = b''.join(dir_parts)
        header = _POSTINGS_HEADER.pack(_POSTINGS_MAGIC, len(terms))
        # After header: dir_size u32, then dir, then postings
        payload = header + struct.pack('<I', len(dir_blob)) + dir_blob + postings_blob
        with open(path, 'wb') as f:
            f.write(payload)

    def open_mmap_postings(self, path: Path) -> bool:
        """Memory-map a .postings sidecar (optional acceleration)."""
        path = Path(path)
        if not path.exists():
            return False
        with open(path, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        # File can be closed after mmap on POSIX; mapping stays valid.
        magic, nterms = _POSTINGS_HEADER.unpack_from(mm, 0)
        if magic != _POSTINGS_MAGIC:
            mm.close()
            return False
        dir_size = struct.unpack_from('<I', mm, 16)[0]
        dir_start = 20
        postings_start = dir_start + dir_size
        term_dir = {}
        pos = dir_start
        end = dir_start + dir_size
        while pos < end:
            tlen, pad, off, count = struct.unpack_from('<HHII', mm, pos)
            pos += 8
            term = mm[pos:pos + tlen].decode('utf-8')
            pos += tlen + pad
            term_dir[term] = (postings_start + off, count)
        self._mmap = mm
        self._mmap_path = path
        self._mmap_term_dir = term_dir
        return True

    def close(self):
        """Release mmap resources if held."""
        mm = getattr(self, '_mmap', None)
        if mm is not None:
            try:
                mm.close()
            except Exception:
                pass
            self._mmap = None

    @classmethod
    def load(cls, filepath: Path) -> 'BM25Index':
        filepath = Path(filepath)

        data = None
        # Try binary pickle first
        candidates = []
        if filepath.exists():
            candidates.append(filepath)
        # Common alternate names beside given path
        parent = filepath.parent
        stem = filepath.name
        for s in ('.json.gz', '.json', '.pkl.gz', '.pkl', '.gz'):
            if stem.endswith(s):
                stem = stem[: -len(s)]
                break
        for name in (stem + '.pkl.gz', stem + '.json.gz', stem + '.json', 'index.pkl.gz', 'index.json.gz'):
            p = parent / name if name != filepath.name else filepath
            if p.exists() and p not in candidates:
                candidates.append(p)

        # Also if path is directory
        if filepath.is_dir():
            for name in ('index.pkl.gz', 'index.json.gz', 'index.json'):
                p = filepath / name
                if p.exists():
                    candidates.insert(0, p)

        last_err = None
        for path in candidates:
            try:
                if str(path).endswith('.pkl.gz') or str(path).endswith('.pkl'):
                    opener = gzip.open if str(path).endswith('.gz') else open
                    with opener(path, 'rb') as f:
                        data = pickle.load(f)
                    filepath = path
                    break
                if str(path).endswith('.gz'):
                    with gzip.open(path, 'rt', encoding='utf-8') as f:
                        data = json.load(f)
                    filepath = path
                    break
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                filepath = path
                break
            except Exception as e:
                last_err = e
                data = None

        if data is None:
            raise FileNotFoundError(f"Could not load index from {filepath}: {last_err}")

        index = cls(k1=data.get('k1', 1.5), b=data.get('b', 0.75), stem=data.get('stem', True))

        # Legacy JSON format: index values are list of [doc_id, tf]
        if 'index' in data and data['index']:
            sample = next(iter(data['index'].values()))
            if sample and isinstance(sample[0], (list, tuple)) and len(sample[0]) == 2:
                # upgrade legacy rows to 4-tuples
                data['index'] = {
                    t: [(int(a), int(b), 0, 0) for a, b in rows]
                    for t, rows in data['index'].items()
                }

        index._restore_state(data)

        # Optional mmap sidecar
        postings_path = filepath.with_name(
            filepath.name.replace('.pkl.gz', '.postings').replace('.json.gz', '.postings')
        )
        if not postings_path.exists():
            postings_path = filepath.parent / 'index.postings'
        try:
            index.open_mmap_postings(postings_path)
        except Exception:
            pass

        return index

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_documents': self.total_docs,
            'unique_terms': len(self.index),
            'bigrams': len(self.bigrams),
            'avg_document_length': round(self.avg_doc_length, 1),
            'k1': self.k1,
            'b': self.b,
            'stemming': self.stem,
            'format_version': INDEX_FORMAT_VERSION,
        }

    def build_symspell(self, max_distance: int = 2) -> SymSpell:
        symspell = SymSpell(max_distance=max_distance)
        clean_terms = filter_suggestion_terms(self.doc_freqs)
        for term, doc_freq in clean_terms.items():
            symspell.add_word(term, frequency=doc_freq)
        return symspell

    def build_ngram_index(self, n: int = 3) -> NGramIndex:
        ngram_index = NGramIndex(n=n)
        clean_terms = filter_suggestion_terms(self.doc_freqs)
        for term, doc_freq in clean_terms.items():
            ngram_index.add_term(term, frequency=doc_freq)
        return ngram_index

    def get_doc_id(self, url: str) -> Optional[int]:
        return self.url_to_id.get(url)

    def get_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        return self.documents.get(doc_id)

    def get_document_frequency(self, term: str) -> Optional[int]:
        postings = self.index.get(term.lower())
        if postings is None:
            return None
        return len(postings)

    def has_url(self, url: str) -> bool:
        return url in self.url_to_id

    def set_click_counts(self, counts: Dict[str, int]):
        """Install CTR data for ranking boosts."""
        self.click_counts = dict(counts or {})
