# Tokenization Behavior

This document explains how doc-search processes text during indexing and search.

## Overview

When you crawl a website and build a search index, text goes through a **tokenization pipeline** that transforms raw content into searchable terms. Understanding this process helps you write better search queries and understand why certain results appear (or don't).

## The Tokenization Pipeline

```
Raw Text → Structured Numbers → Word Extraction → Code Splits → Stop Word Removal → [Optional Stemming]
```

### 1. Case Normalization

All text is converted to lowercase before processing.

```
"Python Programming" → "python programming"
```

This ensures searches are case-insensitive: searching for "Python", "PYTHON", or "python" all match the same documents.

### 2. Word Extraction

Words are extracted with a code-aware scanner that keeps:

- Letter-leading identifiers (`python`, `my_function`, `html5`)
- Digit-leading tokens (`3d`, `7zip`, `64bit`)
- Pure numbers (`1234`, `404`, `7`)
- Structured forms: versions (`3.12`, `2.6.3`), thousands (`1,234` → `1234`), hex (`0x1234`)

Glued alphanumerics are split **and** kept whole:

| Input | Tokens |
|-------|--------|
| `"hello world"` | `hello`, `world` |
| `"ticket1234"` | `ticket`, `1234`, `ticket1234` |
| `"Python 3.12"` | `python`, `3.12`, `3`, `12` |
| `"mask 0x1234"` | `mask`, `0x1234`, `1234` |
| `"3d model"` | `3d`, `3`, `model` |
| `"my_function()"` | `my`, `function`, `my_function` |
| `"os.path.join"` | `os`, `path`, `join` |

**Still filtered:**
- Stop words (`the`, `a`, …)
- Single letters (`x`, `y`) — single digits are kept
- Bare symbols (`@`, `#`, `$`)
- Non-ASCII letters (é, ñ, 中文)

### 3. Stop Word Removal

Common English words that appear in almost every document are removed. These words don't help distinguish between documents.

Programming keywords that are also English glue are **kept** so queries like `async with` stay multi-term: `and`, `or`, `not`, `if`, `else`, `for`, `from`, `with`, `as`, `in`, `on`, `to`, `by`, `at`, `is`.

### 4. Short Word Filtering

Single-character **letters** are removed. Single **digits** are kept so `PEP 8` and chapter `8` remain searchable.

### 5. Optional Stemming

When enabled, alphabetic words are reduced to their root form using the **Porter Stemming Algorithm**. Numeric tokens, versions, and hex are never stemmed.

| Original | Stemmed |
|----------|---------|
| running | run |
| files | file |
| ticket1234 | ticket1234 |
| 3.12 | 3.12 |

## Impact on Search

### What You Can Search For

✅ **Regular words:** `python`, `programming`, `tutorial`  
✅ **Technical terms:** `numpy`, `django`, `api`  
✅ **Numbers:** `1234`, `404`, `2024`  
✅ **Glued IDs:** `ticket1234` or just `1234`  
✅ **Versions / hex:** `3.12`, `0x1234`  
✅ **Digit-leading tokens:** `3d`, `7zip`, `64bit`  
✅ **Quoted phrases:** `"machine learning"` (matches exact sequence)

### What Won't Work

❌ **Stop words alone:** Searching for "the" returns no results  
❌ **Symbols:** `@`, `#`, `$` are stripped  
❌ **Single letters:** `x`, `y`, `z` are filtered out

### Tips for Better Searches

1. **Use specific terms:** Instead of "the python", search for "python"
2. **Use phrases:** `"web server"` matches those words in sequence
3. **Numbers work:** `1234` finds both `ticket 1234` and `ticket1234`
4. **Reindex after tokenizer changes:** `python -m doc_search index <url> --full`

## Customization

To modify tokenization behavior, edit `doc_search/core/text.py`:

- **Add/remove stop words:** Edit the `STOP_WORDS` frozenset
- **Change word pattern:** Modify the scanner in `_raw_tokens()`

After changes, rebuild your index:
```bash
python -m doc_search index <url> --full
```

## Technical Details

### Code Location
- Tokenization: `doc_search/core/text.py` → `tokenize()`
- Stop words: `doc_search/core/text.py` → `STOP_WORDS`
- Stemming: `doc_search/stemmer.py` → `stem()`

### Performance
- Tokenization is O(n) where n is text length
- Stop word lookup uses a frozenset (O(1) lookup)
- Stemmer uses LRU cache (10,000 words) for repeated terms
