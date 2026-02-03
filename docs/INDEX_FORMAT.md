# Index Format Specification

This document describes the BM25 search index file format used by doc-search.

## Overview

The search index is stored as a JSON file (optionally gzip-compressed) containing all data needed to perform BM25-based full-text search without accessing the original documents.

## File Format

### Compression

- **Compressed (default)**: `.json.gz` - gzip-compressed JSON
- **Uncompressed**: `.json` - plain JSON

The `load()` method automatically detects and handles both formats.

### Encoding

- Character encoding: UTF-8
- JSON format: Standard JSON (RFC 8259)

## Schema

```json
{
  "format_version": "1.0",
  "k1": 1.5,
  "b": 0.75,
  "stem": true,
  "documents": {
    "0": {"url": "https://...", "title": "...", "description": "..."},
    "1": {"url": "https://...", "title": "...", "description": "..."}
  },
  "url_to_id": {
    "https://example.com/page1": 0,
    "https://example.com/page2": 1
  },
  "index": {
    "term1": [[0, 5], [1, 2]],
    "term2": [[0, 1]]
  },
  "doc_lengths": {
    "0": 150,
    "1": 200
  },
  "avg_doc_length": 175.0,
  "total_docs": 2,
  "doc_freqs": {
    "term1": 2,
    "term2": 1
  }
}
```

## Field Reference

### Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `format_version` | string | Index format version (currently `"1.0"`) |
| `k1` | float | BM25 term frequency saturation parameter (default: 1.5) |
| `b` | float | BM25 length normalization parameter (default: 0.75, range: 0-1) |
| `stem` | boolean | Whether Porter stemming was applied during indexing |

### Document Storage

| Field | Type | Description |
|-------|------|-------------|
| `documents` | object | Map of document ID (string) → document metadata |
| `documents[id].url` | string | Original document URL |
| `documents[id].title` | string | Document title |
| `documents[id].description` | string | Meta description (may be empty) |
| `url_to_id` | object | Reverse lookup: URL → document ID |

### Inverted Index

| Field | Type | Description |
|-------|------|-------------|
| `index` | object | Map of term → postings list |
| `index[term]` | array | List of `[doc_id, term_frequency]` pairs |

Each posting is a 2-element array:
- `[0]`: Document ID (integer)
- `[1]`: Term frequency in that document (integer)

### Statistics

| Field | Type | Description |
|-------|------|-------------|
| `doc_lengths` | object | Map of document ID (string) → document length in tokens |
| `avg_doc_length` | float | Average document length across all documents |
| `total_docs` | integer | Total number of indexed documents |
| `doc_freqs` | object | Map of term → number of documents containing the term |

## Term Weighting

During indexing, different content types receive different weights:

| Content Type | Weight | Description |
|--------------|--------|-------------|
| Title | 3× | Title tokens are counted 3 times |
| H1 headings | 3× | Level 1 headings |
| H2 headings | 2× | Level 2 headings |
| H3+ headings | 1× | Level 3 and below |
| Body text | 1× | Regular paragraph content |

This weighting is reflected in the term frequencies stored in the index.

## BM25 Parameters

### k1 (Term Frequency Saturation)

- **Default**: 1.5
- **Range**: ≥ 0
- **Effect**: Controls how quickly term frequency saturates
  - Higher values: More weight to repeated terms
  - Lower values: Diminishing returns on term repetition
  - k1 = 0: Binary term presence (frequency ignored)

### b (Length Normalization)

- **Default**: 0.75
- **Range**: 0 to 1
- **Effect**: Controls document length normalization
  - b = 1: Full length normalization (longer docs penalized)
  - b = 0: No length normalization
  - b = 0.75: Balanced (recommended default)

## Version Compatibility

### Version 1.0 (Current)

- Initial stable format
- All fields documented above
- Introduced `format_version` field for future compatibility

### Backward Compatibility

- Indexes without `format_version` are treated as version 1.0
- Indexes without `stem` field default to `stem: true`
- Future versions will include migration logic in the `load()` method

### Forward Compatibility

- Unknown fields are ignored during loading
- Applications should not rely on field ordering
- Numeric document IDs may be stored as strings in JSON

## File Size Considerations

Index size depends on:
- Number of documents
- Vocabulary size (unique terms)
- Average document length
- Whether compression is enabled

Typical compression ratios: 5-10× size reduction with gzip.

## Example: Minimal Valid Index

```json
{
  "format_version": "1.0",
  "k1": 1.5,
  "b": 0.75,
  "stem": true,
  "documents": {},
  "url_to_id": {},
  "index": {},
  "doc_lengths": {},
  "avg_doc_length": 0.0,
  "total_docs": 0,
  "doc_freqs": {}
}
```

## Example: Index with One Document

```json
{
  "format_version": "1.0",
  "k1": 1.5,
  "b": 0.75,
  "stem": true,
  "documents": {
    "0": {
      "url": "https://docs.example.com/getting-started",
      "title": "Getting Started Guide",
      "description": "Learn how to get started with our product."
    }
  },
  "url_to_id": {
    "https://docs.example.com/getting-started": 0
  },
  "index": {
    "get": [[0, 4]],
    "start": [[0, 4]],
    "guid": [[0, 3]],
    "learn": [[0, 1]],
    "product": [[0, 1]]
  },
  "doc_lengths": {
    "0": 13
  },
  "avg_doc_length": 13.0,
  "total_docs": 1,
  "doc_freqs": {
    "get": 1,
    "start": 1,
    "guid": 1,
    "learn": 1,
    "product": 1
  }
}
```

Note: Terms shown are after Porter stemming (e.g., "getting" → "get", "started" → "start", "guide" → "guid").

## Related Documentation

- [API Reference](API.md) - BM25Index class methods
- [Architecture](ARCHITECTURE.md) - System design overview
- [Tokenization](TOKENIZATION.md) - Text processing pipeline
