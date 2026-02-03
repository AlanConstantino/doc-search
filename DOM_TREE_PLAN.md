# DOM Tree Parser Implementation Plan

## Overview
Build a lightweight DOM tree parser using only Python stdlib to enable better content extraction for indexing. The DOM parser will become the new default, with the current streaming parser available via `--parser=stream` flag.

## Goals
1. Parse HTML into a tree structure
2. Enable finding main content area (`<main>`, `<article>`, or largest content block)
3. Better boilerplate removal (nav, header, footer, aside, script, style)
4. Extract text in proper reading order
5. **Stdlib only** — use `html.parser.HTMLParser` as the tokenizer

## Architecture

```
HTML → extract_links() → ALL links (for crawling) [UNCHANGED]
    → extract_text()  → Uses DOM tree for main content detection [NEW]
```

**Important:** Link extraction remains unchanged — gets ALL links from full page for crawling. DOM tree only affects text extraction for indexing.

---

## Phase 1: Core Data Structures (~50 lines)
**File:** `doc_search/dom.py`

### Classes

```python
class Node:
    """Base class for DOM nodes"""
    parent: Optional['Element']
    
    def remove(self) -> None:
        """Detach this node from its parent"""

class Element(Node):
    """HTML element: <tag attrs>children</tag>"""
    tag: str
    attrs: Dict[str, str]
    children: List[Node]
    
    def find(self, tag: str) -> Optional['Element']:
        """Find first matching descendant by tag name"""
    
    def find_all(self, tag: str) -> List['Element']:
        """Find all matching descendants by tag name"""
    
    def get_text(self, separator: str = ' ') -> str:
        """Get all text content concatenated"""
    
    def __iter__(self) -> Iterator[Node]:
        """Iterate over children"""

class Text(Node):
    """Text content between tags"""
    content: str
```

### Estimated: 30 minutes

---

## Phase 2: Tree Builder (~100 lines)
**File:** `doc_search/dom.py` (continued)

### Class: `DOMTreeBuilder(HTMLParser)`

Builds tree while parsing HTML (single pass).

```python
class DOMTreeBuilder(HTMLParser):
    """Build a DOM tree from HTML using stdlib HTMLParser."""
    
    VOID_ELEMENTS = {'br', 'hr', 'img', 'input', 'meta', 'link', ...}
    
    def __init__(self):
        super().__init__()
        self.root = Element('document', {})
        self._stack = [self.root]
    
    def handle_starttag(self, tag, attrs):
        """Create element and push to stack"""
    
    def handle_endtag(self, tag):
        """Pop from stack (with recovery for malformed HTML)"""
    
    def handle_data(self, data):
        """Create text node and append to current element"""
    
    def handle_startendtag(self, tag, attrs):
        """Handle self-closing tags like <br/>"""
```

### Features
- Maintains stack of open elements
- Handles malformed HTML (missing close tags, misnested tags)
- Auto-closes void elements (`<br>`, `<img>`, `<meta>`, etc.)
- Graceful error recovery (like browsers)

### Usage
```python
builder = DOMTreeBuilder()
builder.feed(html)
root = builder.root  # Document root element
```

### Estimated: 1 hour

---

## Phase 3: Content Extraction (~100 lines)
**File:** `doc_search/dom.py` (continued)

### Function: `extract_main_content(root: Element) -> Element`

Algorithm to find the main content area:

1. Look for `<main>` tag → return if found
2. Look for `<article>` tag → return if found
3. Score all `<div>` elements by text density:
   - `score = text_length / (1 + descendant_tag_count)`
   - Higher score = more content, fewer nested tags
4. Return highest-scoring `<div>`
5. Fallback: return `<body>` or root

### Function: `strip_boilerplate(element: Element) -> None`

Remove boilerplate elements in-place:
- `<script>`, `<style>`, `<noscript>`
- `<nav>`, `<header>`, `<footer>`, `<aside>`
- Elements with common boilerplate classes/ids (optional heuristic)

### Function: `extract_text_dom(html: str) -> Dict[str, Any]`

Main entry point — returns same format as current `extract_text()`:
```python
{
    'title': str,           # From <title> tag
    'description': str,     # From <meta name="description">
    'text': str,            # Main content text
    'headings': List[Tuple[int, str]]  # [(level, text), ...]
}
```

### Implementation
```python
def extract_text_dom(html: str, include_nav: bool = False) -> Dict[str, Any]:
    # Build tree
    builder = DOMTreeBuilder()
    builder.feed(html)
    root = builder.root
    
    # Extract metadata (from full document)
    title = extract_title(root)
    description = extract_meta_description(root)
    
    # Find main content
    body = root.find('body') or root
    if not include_nav:
        strip_boilerplate(body)
    main = extract_main_content(body)
    
    # Extract text and headings
    text = main.get_text()
    headings = extract_headings(main)
    
    return {'title': title, 'description': description, 'text': text, 'headings': headings}
```

### Estimated: 1 hour

---

## Phase 4: Integration (~50 lines)

### CLI Changes

**New flag for `crawl` command:**
```
--parser=dom|stream    Parser for text extraction (default: dom)
```

**New flag for `index` command:**
```
--parser=dom|stream    Parser for text extraction (default: dom)
```

### Files to modify
- `doc_search/cli/parsers.py` — add `--parser` argument
- `doc_search/cli/commands.py` — pass parser choice to crawler/indexer
- `doc_search/crawler/processor.py` — use selected parser
- `doc_search/parser.py` — add `extract_text_dom` import/dispatch

### Behavior
```bash
# New default (DOM tree)
doc-search crawl https://example.com
doc-search index

# Explicit legacy streaming parser
doc-search crawl https://example.com --parser=stream
doc-search index --parser=stream
```

### Backward compatibility
- Default changes from stream → dom
- Existing behavior available via `--parser=stream`
- No changes to link extraction (always extracts all links)

### Estimated: 30 minutes

---

## Phase 5: Documentation (~30 minutes)

### Files to update

1. **README.md**
   - Document new `--parser` flag
   - Explain DOM vs streaming parser differences
   - Update examples

2. **CHANGELOG.md**
   - Add entry for DOM tree parser feature

3. **docs/architecture.md** (if exists)
   - Document DOM tree implementation
   - Explain content extraction algorithm

4. **CLI help text**
   - Ensure `--parser` flag has clear help text
   - Document in `parsers.py`

5. **Code docstrings**
   - Document all new classes/functions in `dom.py`
   - Update `extract_text()` docstring to mention DOM alternative

### Estimated: 30 minutes

---

## Summary

| Phase | Description | Lines | Time |
|-------|-------------|-------|------|
| 1 | Core data structures (Node, Element, Text) | ~50 | 30 min |
| 2 | Tree builder (DOMTreeBuilder) | ~100 | 1 hour |
| 3 | Content extraction (main content, boilerplate) | ~100 | 1 hour |
| 4 | Integration (CLI flags, wiring) | ~50 | 30 min |
| 5 | Documentation updates | — | 30 min |
| **Total** | | **~300** | **3.5 hours** |

---

## Testing Strategy

1. **Unit tests for Node operations**
   - find(), find_all(), get_text(), remove()
   - Tree traversal

2. **Tree builder tests**
   - Well-formed HTML
   - Malformed HTML (missing tags, misnested)
   - Void elements
   - Edge cases (empty document, only text)

3. **Content extraction tests**
   - Pages with `<main>` tag
   - Pages with `<article>` tag
   - Pages with neither (div scoring)
   - Boilerplate stripping

4. **Integration tests**
   - Compare DOM vs streaming output on real pages
   - Ensure backward compatibility with `--parser=stream`

5. **Regression tests**
   - Existing test suite should pass with `--parser=stream`

---

## Open Questions (Resolved)

1. ✅ DOM is new default, streaming via `--parser=stream`
2. ✅ Just use `index` command, no separate `reindex`
3. ✅ Link extraction unchanged — gets ALL links from full page
