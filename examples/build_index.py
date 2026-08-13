#!/usr/bin/env python3
"""
Building a Search Index Example

This example demonstrates how to build a BM25 search index from
crawled pages or from documents you add manually.

Run from repository root:
    python examples/build_index.py

Prerequisites:
    Run basic_crawl.py first, OR this example will create sample
    documents in memory to demonstrate the indexing API.
"""

import json
import tempfile
from pathlib import Path

# Import from doc_search package
from doc_search.index import BM25Index
from doc_search.core import site_hash, format_size


def demo_manual_indexing():
    """
    Demonstrate adding documents to an index manually.
    
    This is useful when you have your own documents (not from crawling)
    that you want to make searchable.
    """
    print("\n" + "=" * 60)
    print("Part 1: Manual Document Indexing")
    print("=" * 60)
    
    # =========================================================================
    # Create a BM25 Index
    # =========================================================================
    
    # BM25 parameters control relevance scoring:
    #   k1: Controls term frequency saturation (typical: 1.2-2.0)
    #        Higher = term frequency matters more
    #   b:  Controls document length normalization (typical: 0.5-0.8)
    #        Higher = longer documents are penalized more
    #   stem: Whether to apply Porter stemming (e.g., "running" -> "run")
    
    index = BM25Index(
        k1=1.5,      # Default: 1.5
        b=0.75,      # Default: 0.75
        stem=True    # Default: True (recommended for English)
    )
    
    print("\nCreated BM25Index with parameters:")
    print(f"  k1 (term frequency saturation): {index.k1}")
    print(f"  b (length normalization): {index.b}")
    print(f"  Stemming: {'enabled' if index.stem else 'disabled'}")
    
    # =========================================================================
    # Add Documents Manually
    # =========================================================================
    
    # Sample documents about Python programming
    documents = [
        {
            "url": "https://example.com/python/intro",
            "title": "Introduction to Python",
            "text": """
                Python is a high-level, interpreted programming language known for 
                its clear syntax and readability. It supports multiple programming 
                paradigms including procedural, object-oriented, and functional 
                programming. Python is widely used in web development, data science,
                artificial intelligence, and automation.
            """,
            "description": "Learn the basics of Python programming language.",
        },
        {
            "url": "https://example.com/python/lists",
            "title": "Python Lists and List Comprehensions",
            "text": """
                Lists are one of Python's most versatile data structures. A list 
                is an ordered collection of items that can be of different types.
                List comprehensions provide a concise way to create lists based on
                existing lists. The syntax is [expression for item in iterable].
                For example: squares = [x**2 for x in range(10)].
            """,
            "description": "Understanding Python lists and list comprehensions.",
        },
        {
            "url": "https://example.com/python/functions",
            "title": "Python Functions and Decorators",
            "text": """
                Functions in Python are defined using the def keyword. They can 
                accept arguments and return values. Python supports default arguments,
                keyword arguments, and variable-length arguments (*args, **kwargs).
                Decorators are a powerful feature that allows you to modify or extend
                the behavior of functions without changing their code.
            """,
            "description": "Learn about Python functions, arguments, and decorators.",
        },
        {
            "url": "https://example.com/python/classes",
            "title": "Object-Oriented Programming in Python",
            "text": """
                Python supports object-oriented programming with classes and objects.
                A class is a blueprint for creating objects. Classes can have attributes
                (data) and methods (functions). Python supports inheritance, allowing
                classes to inherit from other classes. Special methods like __init__
                and __str__ customize class behavior.
            """,
            "description": "Learn OOP concepts in Python: classes, objects, inheritance.",
        },
    ]
    
    print(f"\nAdding {len(documents)} documents to the index...")
    
    for doc_id, doc in enumerate(documents):
        index.add_document(
            doc_id=doc_id,
            url=doc["url"],
            title=doc["title"],
            text=doc["text"],
            description=doc["description"],
            headings=[]  # Optional: list of (level, text) tuples for headings
        )
        print(f"  Added: {doc['title']}")
    
    # =========================================================================
    # Examine Index Statistics
    # =========================================================================
    
    stats = index.get_stats()
    print("\n📊 Index Statistics:")
    print(f"  Total documents: {stats['total_documents']}")
    print(f"  Unique terms: {stats['unique_terms']}")
    print(f"  Average document length: {stats['avg_document_length']} terms")
    
    # =========================================================================
    # Perform a Basic Search
    # =========================================================================
    
    print("\n🔍 Testing search...")
    
    queries = ["list comprehension", "decorators", "object oriented"]
    
    for query in queries:
        results = index.search(query, top_k=2)
        print(f"\n  Query: '{query}'")
        for r in results:
            print(f"    - {r['title']} (score: {r['score']:.4f})")
    
    # =========================================================================
    # Save and Load the Index
    # =========================================================================
    
    print("\n💾 Saving and loading index...")
    
    # Create a temporary directory for this demo
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / "demo_index"
        
        # Save with compression (default)
        saved_path = index.save(index_path, compress=True)
        file_size = saved_path.stat().st_size
        print(f"  Saved to: {saved_path}")
        print(f"  File size: {format_size(file_size)}")
        
        # Load it back
        loaded_index = BM25Index.load(saved_path)
        loaded_stats = loaded_index.get_stats()
        print(f"  Loaded: {loaded_stats['total_documents']} documents, {loaded_stats['unique_terms']} terms")
        
        # Verify search still works
        results = loaded_index.search("python programming", top_k=1)
        if results:
            print(f"  Search test passed: found '{results[0]['title']}'")
    
    return index


def demo_crawled_indexing():
    """
    Demonstrate building an index from crawled pages.
    
    This requires running basic_crawl.py first.
    """
    print("\n" + "=" * 60)
    print("Part 2: Building Index from Crawled Pages")
    print("=" * 60)
    
    # Check if we have crawled data
    base_url = "https://httpbin.org"
    site_dir = Path.home() / ".doc_search" / "sites" / site_hash(base_url)
    pages_dir = site_dir / "pages"
    
    if not pages_dir.exists():
        print(f"\n⚠️  No crawled pages found at: {pages_dir}")
        print("   Run basic_crawl.py first to crawl a site.")
        print("   Skipping this part of the demo.")
        return None
    
    page_files = list(pages_dir.glob("*.json"))
    if not page_files:
        print(f"\n⚠️  No page files found in: {pages_dir}")
        return None
    
    print(f"\nFound {len(page_files)} crawled pages in: {pages_dir}")
    
    # =========================================================================
    # Build Index from Crawled Pages
    # =========================================================================
    
    index = BM25Index(k1=1.5, b=0.75, stem=True)
    
    print("\nBuilding index from crawled pages...")
    
    # The build_from_pages method handles loading JSON files
    # and extracting title, text, description, and headings
    num_docs = index.build_from_pages(pages_dir, verbose=True)
    
    if num_docs == 0:
        print("⚠️  No documents were indexed (pages may be empty)")
        return None
    
    # =========================================================================
    # Save the Index
    # =========================================================================
    
    index_path = site_dir / "index"
    saved_path = index.save(index_path, compress=True)
    
    print(f"\n✅ Index saved to: {saved_path}")
    print(f"   Size: {format_size(saved_path.stat().st_size)}")
    
    # =========================================================================
    # Quick Search Test
    # =========================================================================
    
    print("\n🔍 Quick search test:")
    results = index.search("http", top_k=3)
    
    if results:
        for r in results:
            print(f"  - {r['title'] or r['url']} (score: {r['score']:.4f})")
    else:
        print("  No results found (try a different query)")
    
    return index


def main():
    print("=" * 60)
    print("doc-search: Building Search Index Example")
    print("=" * 60)
    
    # Part 1: Manual indexing (always runs)
    demo_manual_indexing()
    
    # Part 2: From crawled pages (requires running basic_crawl.py first)
    demo_crawled_indexing()
    
    # =========================================================================
    # Next Steps
    # =========================================================================
    
    print("\n" + "=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print("1. Search the index: python examples/search_example.py")
    print("2. Full pipeline:    python examples/full_pipeline.py")
    print("3. Or use the CLI:   python -m doc_search search <url> 'query'")


if __name__ == "__main__":
    main()
