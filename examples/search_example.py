#!/usr/bin/env python3
"""
Searching Programmatically Example

This example demonstrates how to use the search API to search
an existing index with various features.

Run from repository root:
    python examples/search_example.py

Prerequisites:
    This example works best after running basic_crawl.py and build_index.py,
    but it will also create a demo index if no crawled data exists.
"""

import tempfile
from pathlib import Path

# Import from doc_search package
from doc_search.indexer import BM25Index
from doc_search.searcher import SearchEngine, EnhancedSearchEngine
from doc_search.utils import site_hash


def create_demo_index():
    """
    Create a demo index with sample documents.
    Returns (index, pages_dir) where pages_dir may be None.
    """
    index = BM25Index(k1=1.5, b=0.75, stem=True)
    
    # Sample documents
    documents = [
        {
            "url": "https://docs.python.org/tutorial/introduction.html",
            "title": "Introduction to Python",
            "text": """
                Python is an easy to learn, powerful programming language. It has
                efficient high-level data structures and a simple but effective 
                approach to object-oriented programming. Python's elegant syntax
                and dynamic typing make it ideal for scripting and rapid application
                development. The Python interpreter and standard library are available
                for all major platforms.
            """,
            "description": "An informal introduction to Python.",
        },
        {
            "url": "https://docs.python.org/tutorial/datastructures.html",
            "title": "Data Structures in Python",
            "text": """
                This chapter describes some things you've learned about already in 
                more detail, and adds some new things as well. Lists are mutable
                sequences, typically used to store collections of homogeneous items.
                List comprehensions provide a concise way to create lists. The 
                syntax is [expression for item in iterable if condition]. Tuples
                are immutable sequences. Dictionaries are mutable mappings.
            """,
            "description": "Learn about Python's built-in data structures.",
        },
        {
            "url": "https://docs.python.org/tutorial/errors.html",
            "title": "Errors and Exceptions",
            "text": """
                Until now error messages haven't been more than mentioned. Python
                distinguishes between syntax errors and exceptions. Syntax errors
                are parsing errors. Exceptions are errors detected during execution.
                The try statement works as follows: first the try clause is executed.
                If no exception occurs, the except clause is skipped. If an exception
                occurs, the except clause handles it. Use finally for cleanup actions.
            """,
            "description": "Handling errors and exceptions in Python.",
        },
        {
            "url": "https://docs.python.org/tutorial/classes.html",
            "title": "Classes and Object-Oriented Programming",
            "text": """
                Classes provide a means of bundling data and functionality together.
                Creating a new class creates a new type of object. Each class instance
                can have attributes attached to it. Class instances can also have
                methods. Python supports inheritance, allowing derived classes to
                override methods. Multiple inheritance is also supported. Use super()
                to call parent class methods.
            """,
            "description": "Introduction to classes in Python.",
        },
        {
            "url": "https://docs.python.org/tutorial/modules.html",
            "title": "Modules and Packages",
            "text": """
                A module is a file containing Python definitions and statements.
                The file name is the module name with .py appended. Modules can
                import other modules. The import statement imports names from a
                module. The from...import statement imports specific names. Packages
                are a way of structuring Python's module namespace. The __init__.py
                file is required to make Python treat directories as packages.
            """,
            "description": "Understanding Python modules and packages.",
        },
    ]
    
    for doc_id, doc in enumerate(documents):
        index.add_document(
            doc_id=doc_id,
            url=doc["url"],
            title=doc["title"],
            text=doc["text"],
            description=doc["description"],
        )
    
    return index


def demo_basic_search(engine: SearchEngine):
    """Demonstrate basic search functionality."""
    print("\n" + "-" * 60)
    print("Basic Search")
    print("-" * 60)
    
    query = "list comprehension"
    print(f"\n🔍 Query: '{query}'")
    
    results = engine.search(
        query=query,
        top_k=3,           # Number of results
        highlight=True,    # Highlight matching terms in snippets
        snippet_length=100 # Target snippet length
    )
    
    print(f"   Found {len(results)} results:\n")
    
    for i, result in enumerate(results, 1):
        print(f"   {i}. {result['title']}")
        print(f"      URL: {result['url']}")
        print(f"      Score: {result['score']:.4f}")
        if result.get('snippet'):
            # Snippet may contain <mark> tags for highlighting
            snippet = result['snippet'].replace('<mark>', '**').replace('</mark>', '**')
            print(f"      Snippet: {snippet[:100]}...")
        print()


def demo_phrase_search(engine: SearchEngine):
    """Demonstrate exact phrase search."""
    print("\n" + "-" * 60)
    print("Phrase Search (Exact Match)")
    print("-" * 60)
    
    # Use quotes for exact phrase matching
    query = '"object-oriented programming"'
    print(f'\n🔍 Query: {query}')
    print("   (Quotes require the exact phrase to appear in results)")
    
    results = engine.search(query, top_k=3)
    
    print(f"   Found {len(results)} results:\n")
    
    for i, result in enumerate(results, 1):
        print(f"   {i}. {result['title']}")
        print(f"      Score: {result['score']:.4f}")


def demo_enhanced_features(enhanced_engine: EnhancedSearchEngine):
    """Demonstrate enhanced search features."""
    print("\n" + "-" * 60)
    print("Enhanced Search Features")
    print("-" * 60)
    
    # =========================================================================
    # Spelling Suggestions
    # =========================================================================
    
    print("\n📝 Spelling Suggestions:")
    
    # Intentional typo
    typo_query = "pyhton progamming"
    suggestion = enhanced_engine.get_spelling_suggestion(typo_query)
    
    print(f"   Query: '{typo_query}'")
    if suggestion:
        print(f"   Did you mean: '{suggestion}'")
    else:
        print("   No suggestion (query looks correct)")
    
    # =========================================================================
    # Autocomplete
    # =========================================================================
    
    print("\n⌨️  Autocomplete Suggestions:")
    
    prefix = "class"
    suggestions = enhanced_engine.get_suggestions(prefix, max_suggestions=5)
    
    print(f"   Prefix: '{prefix}'")
    print(f"   Suggestions: {suggestions}")
    
    # =========================================================================
    # Search with All Features
    # =========================================================================
    
    print("\n🔍 Enhanced Search (with all features):")
    
    query = "exception handling"
    
    # search_enhanced() returns a dict with results AND metadata
    response = enhanced_engine.search_enhanced(
        query=query,
        top_k=3,
        use_synonyms=False  # Set True to expand with synonyms
    )
    
    print(f"   Query: '{query}'")
    print(f"   Results: {len(response['results'])}")
    
    if response.get('suggestion'):
        print(f"   Suggestion: '{response['suggestion']}'")
    
    if response.get('expanded_query'):
        print(f"   Expanded query: '{response['expanded_query']}'")
    
    print("\n   Top results:")
    for i, result in enumerate(response['results'][:3], 1):
        print(f"   {i}. {result['title']} (score: {result['score']:.4f})")
    
    # =========================================================================
    # Faceted Search
    # =========================================================================
    
    print("\n📁 Faceted Search:")
    
    # Get facet counts from results
    facets = enhanced_engine.get_facet_counts(response['results'])
    
    if facets:
        print("   Available facets:")
        for facet_type, values in facets.items():
            print(f"   - {facet_type}:")
            for value, count in list(values.items())[:3]:
                print(f"       {value}: {count}")
    else:
        print("   No facets available for these results")


def demo_search_statistics(engine: SearchEngine):
    """Show search engine statistics."""
    print("\n" + "-" * 60)
    print("Index Statistics")
    print("-" * 60)
    
    stats = engine.get_stats()
    
    print("\n📊 Index Statistics:")
    for key, value in stats.items():
        print(f"   {key}: {value}")


def main():
    print("=" * 60)
    print("doc-search: Searching Programmatically Example")
    print("=" * 60)
    
    # =========================================================================
    # Try to Load Existing Index, or Create Demo Index
    # =========================================================================
    
    # Check for existing crawled data
    base_url = "https://httpbin.org"
    site_dir = Path.home() / ".doc_search" / "sites" / site_hash(base_url)
    index_path = site_dir / "index.json.gz"
    
    if index_path.exists():
        print(f"\n📂 Loading existing index from: {index_path}")
        engine = SearchEngine.load(index_path)
        enhanced_engine = EnhancedSearchEngine.load(
            index_path,
            enable_spellcheck=True,
            enable_autocomplete=True,
            enable_facets=True,
            enable_synonyms=False
        )
    else:
        print("\n📂 No existing index found, creating demo index...")
        print("   (Run basic_crawl.py and build_index.py for real data)")
        
        # Create demo index
        index = create_demo_index()
        
        # Wrap in search engines
        engine = SearchEngine(index, pages_dir=None)
        enhanced_engine = EnhancedSearchEngine(
            index,
            pages_dir=None,
            enable_spellcheck=True,
            enable_autocomplete=True,
            enable_facets=True,
            enable_synonyms=False
        )
    
    # =========================================================================
    # Demonstrate Various Search Features
    # =========================================================================
    
    # Basic search
    demo_basic_search(engine)
    
    # Phrase search
    demo_phrase_search(engine)
    
    # Enhanced features (spellcheck, autocomplete, facets)
    demo_enhanced_features(enhanced_engine)
    
    # Statistics
    demo_search_statistics(engine)
    
    # =========================================================================
    # Next Steps
    # =========================================================================
    
    print("\n" + "=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print("1. Full pipeline:     python examples/full_pipeline.py")
    print("2. Interactive CLI:   python -m doc_search interactive <url>")
    print("3. Web UI:            python -m doc_search serve <url> --open")


if __name__ == "__main__":
    main()
