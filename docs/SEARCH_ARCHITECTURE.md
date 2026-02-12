# doc-search Query Architecture

## Overview

Two-pass retrieval system with spelling suggestions and fuzzy fallback, modeled after Confluence/Lucene search behavior.

## Components

### SymSpell (Suggestions Only)
- **Purpose**: Generate "Did you mean?" suggestions for display
- **When**: Runs BEFORE BM25 search
- **Behavior**: 
  - Checks query terms against vocabulary
  - Suggests correct terms for typos
  - Does NOT auto-execute the corrected query
  - User must click suggestion to re-search

### Levenshtein Automaton (Recall Fallback)
- **Purpose**: Expand query when initial search returns weak results
- **When**: Runs AFTER BM25 Pass 1, only if results < MIN_RESULTS
- **Behavior**:
  - Finds vocabulary terms within edit distance of OOV terms
  - Triggers second BM25 pass with expanded terms
  - Expansions are downweighted in scoring

### BM25 + Reranking
- **Purpose**: Core retrieval and ranking
- **When**: Always runs (Pass 1), optionally Pass 2 if weak results
- **Behavior**:
  - BM25 for initial candidate retrieval
  - Two-stage reranking with field-aware scoring

---

## Query Flow

```
User Query: "pythom tutrial"
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                      QUERY PARSING                          │
│  • Extract terms, phrases, wildcards                        │
│  • "pythom", "tutrial"                                      │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                    SYMSPELL CHECK                           │
│  • Check each term against vocabulary                       │
│  • Generate suggestion: "python tutorial"                   │
│  • Store for display (DO NOT modify query)                  │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                     BM25 PASS 1                             │
│  • Search with ORIGINAL terms: "pythom", "tutrial"          │
│  • Apply synonyms, wildcards (if any)                       │
│  • NO fuzzy expansion yet                                   │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                   RESULTS CHECK                             │
│  • Count results from Pass 1                                │
│  • MIN_RESULTS threshold (e.g., 5)                          │
└─────────────────────────────────────────────────────────────┘
              │
              ├────── Results >= MIN_RESULTS ──────┐
              │       (good enough, skip fuzzy)    │
              │                                     │
     Results < MIN_RESULTS                         │
        (weak, need recall)                        │
              │                                     │
              ▼                                     │
┌─────────────────────────────┐                    │
│    LEVENSHTEIN EXPANSION    │                    │
│  • Only for OOV terms       │                    │
│  • "pythom" → "python"      │                    │
│  • "tutrial" → "tutorial"   │                    │
│  • Apply smart rules:       │                    │
│    - Skip if len < 4        │                    │
│    - Skip wildcards         │                    │
│    - Skip quoted terms      │                    │
│    - Cap by term length     │                    │
└─────────────────────────────┘                    │
              │                                     │
              ▼                                     │
┌─────────────────────────────┐                    │
│       BM25 PASS 2           │                    │
│  • Search with expanded     │                    │
│    terms (weighted):        │                    │
│    - Original: 1.0          │                    │
│    - Fuzzy dist 1: 0.35     │                    │
│    - Fuzzy dist 2: 0.15     │                    │
└─────────────────────────────┘                    │
              │                                     │
              ▼                                     ▼
┌─────────────────────────────────────────────────────────────┐
│                      RERANKING                              │
│  • Field-aware scoring (title 5x, headings 2.5x)            │
│  • Phrase proximity boosting                                │
│  • Query term coverage boosting                             │
│  • Weighted term expansion scoring                          │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                    FINAL OUTPUT                             │
│  • Ranked results                                           │
│  • "Did you mean: python tutorial?" (from SymSpell)         │
│  • Facets, snippets, highlights                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Smart Rules for Levenshtein Expansion

### ALLOW fuzzy when:
| Condition | Rationale |
|-----------|-----------|
| Term NOT in vocabulary | Likely a typo |
| Pass 1 returned < MIN_RESULTS | Need recall boost |

### BLOCK fuzzy when:
| Condition | Rationale |
|-----------|-----------|
| Term length < 4 | Too many false positives |
| Term contains wildcard `*` | Already handled by n-gram |
| Term in quotes | User wants exact match |
| Term looks like code/ID | `x86_64`, `sha256`, etc. |
| Term in vocab with decent df | Not a typo |

### Distance caps by term length:
| Term Length | Max Edit Distance |
|-------------|-------------------|
| 4 chars | 1 |
| 5-6 chars | 1 |
| 7+ chars | 2 |

### Expansion limits:
- Max 3-5 expansions per term
- Prefer higher document frequency matches

---

## Weights for Expanded Terms

| Source | Weight | Rationale |
|--------|--------|-----------|
| Original term | 1.0 | Exact user intent |
| Synonym | 0.5 | Known equivalence |
| Wildcard expansion | 0.4 | Prefix match |
| Levenshtein dist 1 | 0.35 | Likely typo |
| Levenshtein dist 2 | 0.15 | Possible typo |

---

## Configuration Options

```python
# Suggested defaults
MIN_RESULTS = 5          # Threshold for triggering Pass 2
MAX_FUZZY_EXPANSIONS = 5 # Per term
MIN_TERM_LENGTH = 4      # For fuzzy matching
DF_MIN = 3               # Minimum doc frequency for suggestions
```

---

## Example Scenarios

### Scenario 1: Good results, no fuzzy needed
```
Query: "python tutorial"
Pass 1: 150 results
→ Skip Pass 2, return results + no suggestion needed
```

### Scenario 2: Typo with weak results
```
Query: "pythom tutrial"
SymSpell: "Did you mean: python tutorial?"
Pass 1: 0 results (terms not in vocab)
→ Trigger Pass 2 with Levenshtein expansion
Pass 2: 150 results (searching "python", "tutorial")
→ Return results + suggestion
```

### Scenario 3: Partial typo
```
Query: "pythom basics"
SymSpell: "Did you mean: python basics?"
Pass 1: 3 results (from "basics" alone)
→ Trigger Pass 2 (< MIN_RESULTS)
Pass 2: 45 results (added "python" expansion)
→ Return results + suggestion
```

### Scenario 4: Exact phrase (no fuzzy)
```
Query: "pythom basics" (with quotes... wait, that doesn't make sense)
Query: pythom "list comprehension"
SymSpell: "Did you mean: python "list comprehension"?"
Pass 1: 0 results
→ Trigger Pass 2, but "list comprehension" is NOT fuzzy expanded (quoted)
→ Only "pythom" → "python" expanded
```
