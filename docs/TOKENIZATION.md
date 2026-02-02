# Tokenization Behavior

This document explains how doc-search processes text during indexing and search.

## Overview

When you crawl a website and build a search index, text goes through a **tokenization pipeline** that transforms raw content into searchable terms. Understanding this process helps you write better search queries and understand why certain results appear (or don't).

## The Tokenization Pipeline

```
Raw Text → Lowercase → Word Extraction → Stop Word Removal → Short Word Filtering → [Optional Stemming]
```

### 1. Case Normalization

All text is converted to lowercase before processing.

```
"Python Programming" → "python programming"
```

This ensures searches are case-insensitive: searching for "Python", "PYTHON", or "python" all match the same documents.

### 2. Word Extraction

Words are extracted using a regex pattern that matches:
- Must **start with a letter** (a-z)
- Can contain **letters, digits, or underscores** after the first character

**Pattern:** `[a-z][a-z0-9_]*`

**Examples:**

| Input | Extracted Words |
|-------|-----------------|
| `"hello world"` | `['hello', 'world']` |
| `"Python3.9"` | `['python3']` |
| `"my_function()"` | `['my_function']` |
| `"version 2.0"` | `['version']` |
| `"$100 price"` | `['price']` |
| `"123abc"` | `['abc']` |

**What gets filtered:**
- Pure numbers (`123`, `2.0`)
- Symbols and punctuation
- Words starting with numbers
- Non-ASCII characters (é, ñ, 中文)

### 3. Stop Word Removal

Common English words that appear in almost every document are removed. These words don't help distinguish between documents.

**Full Stop Word List (125 words):**

| Category | Words |
|----------|-------|
| **Articles** | a, an, the |
| **Prepositions** | about, above, after, against, at, before, below, between, by, down, during, for, from, in, into, of, off, on, once, out, over, through, to, under, until, up, with |
| **Conjunctions** | and, as, but, if, nor, or, so, than, that, then, which |
| **Pronouns** | he, her, him, his, i, it, its, me, my, our, she, their, them, they, us, we, who, you, your |
| **Auxiliary Verbs** | am, are, be, been, being, did, do, does, doing, had, has, have, is, was, were |
| **Modal Verbs** | can, could, might, must, shall, should, will, would |
| **Adverbs** | again, also, else, ever, here, how, just, now, only, same, there, too, very, when, where, why |
| **Quantifiers** | all, any, both, each, every, few, more, most, no, not, other, some, such |

### 4. Short Word Filtering

Single-character tokens are removed since they're typically not meaningful for search:
- Most single letters are already stop words (`a`, `i`)
- Remaining single letters are usually noise from tokenization

**Example:**
```
"A B C test" → ['test']
```

### 5. Optional Stemming

When enabled, words are reduced to their root form using the **Porter Stemming Algorithm**.

| Original | Stemmed |
|----------|---------|
| running | run |
| files | file |
| programming | program |
| caresses | caress |
| agreed | agre |

Stemming helps match related word forms but can occasionally produce unexpected results.

## Impact on Search

### What You Can Search For

✅ **Regular words:** `python`, `programming`, `tutorial`  
✅ **Technical terms:** `numpy`, `django`, `api`  
✅ **Mixed alphanumeric:** `python3`, `html5`, `oauth2`  
✅ **Underscored terms:** `my_function`, `user_id`  
✅ **Quoted phrases:** `"machine learning"` (matches exact sequence)

### What Won't Work

❌ **Stop words alone:** Searching for "the" or "and" returns no results  
❌ **Pure numbers:** Searching for `404` or `2024` won't match  
❌ **Symbols:** `@`, `#`, `$` are stripped  
❌ **Single letters:** `x`, `y`, `z` are filtered out

### Tips for Better Searches

1. **Use specific terms:** Instead of "the python", search for "python"
2. **Use phrases:** `"web server"` matches those words in sequence
3. **Technical terms work well:** API names, function names, etc. are preserved
4. **Skip common words:** Don't include "the", "a", "is" in your queries

## Customization

To modify tokenization behavior, edit `doc_search/utils.py`:

- **Add/remove stop words:** Edit the `STOP_WORDS` frozenset
- **Change word pattern:** Modify the regex in `tokenize()`
- **Disable short word filtering:** Remove `len(w) > 1` check

After changes, rebuild your index:
```bash
python -m doc_search index <url>
```

## Technical Details

### Code Location
- Tokenization: `doc_search/utils.py` → `tokenize()`
- Stop words: `doc_search/utils.py` → `STOP_WORDS`
- Stemming: `doc_search/stemmer.py` → `stem()`

### Performance
- Tokenization is O(n) where n is text length
- Stop word lookup uses a frozenset (O(1) lookup)
- Stemmer uses LRU cache (10,000 words) for repeated terms
