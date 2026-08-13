#!/usr/bin/env python3
"""
Full Pipeline Demo: Crawl → Index → Search

This example demonstrates the complete doc-search workflow from start
to finish. It crawls a small site, builds an index, and performs searches,
all in one script.

Run from repository root:
    python examples/full_pipeline.py

Note: This example creates a temporary directory for all data, which is
cleaned up when the script finishes. To persist data, modify the data_dir
to use a permanent location.
"""

import json
import tempfile
import shutil
from pathlib import Path

# Import from doc_search package
from doc_search.crawl import Crawler
from doc_search.index import BM25Index
from doc_search.search import SearchEngine, EnhancedSearchEngine
from doc_search.core import format_size, format_duration


def crawl_site(base_url: str, data_dir: Path, max_pages: int = 10) -> dict:
    """
    Stage 1: Crawl a website.
    
    Args:
        base_url: The URL to start crawling from
        data_dir: Directory to store crawled data
        max_pages: Maximum number of pages to crawl
        
    Returns:
        Crawl statistics dictionary
    """
    print("\n" + "=" * 60)
    print("STAGE 1: CRAWLING")
    print("=" * 60)
    
    print(f"\n🌐 Target: {base_url}")
    print(f"📁 Data directory: {data_dir}")
    print(f"📄 Max pages: {max_pages}")
    
    # Create the crawler
    crawler = Crawler(
        base_url=base_url,
        data_dir=data_dir,
        delay=0.5,          # Be polite - wait between requests
        timeout=30.0,       # Request timeout
        max_pages=max_pages,
        max_depth=3,        # Don't go too deep
        workers=1,          # Single worker for simplicity
        extract_docs=False, # Set True to also extract PDF text
        verbose=True,
    )
    
    print("\n🕷️ Starting crawl...\n")
    
    # Run the crawl
    stats = crawler.crawl(resume=False)  # Start fresh
    
    print(f"\n✅ Crawl complete!")
    print(f"   Pages crawled: {stats.get('pages_crawled', 0)}")
    print(f"   Pages skipped: {stats.get('pages_skipped', 0)}")
    print(f"   Errors: {stats.get('errors', 0)}")
    
    # Save metadata
    metadata = {"url": base_url, "stats": stats}
    with open(data_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    
    return stats


def build_index(data_dir: Path) -> BM25Index:
    """
    Stage 2: Build search index from crawled pages.
    
    Args:
        data_dir: Directory containing crawled pages
        
    Returns:
        The built BM25Index
    """
    print("\n" + "=" * 60)
    print("STAGE 2: INDEXING")
    print("=" * 60)
    
    pages_dir = data_dir / "pages"
    
    if not pages_dir.exists():
        raise FileNotFoundError(f"No pages directory found at {pages_dir}")
    
    page_count = len(list(pages_dir.glob("*.json")))
    print(f"\n📂 Found {page_count} page files")
    
    # Create the index
    index = BM25Index(
        k1=1.5,   # Term frequency saturation
        b=0.75,   # Document length normalization
        stem=True # Apply Porter stemming
    )
    
    print("\n🔨 Building index...\n")
    
    # Build from page files
    num_docs = index.build_from_pages(pages_dir, verbose=True)
    
    if num_docs == 0:
        print("⚠️ Warning: No documents were indexed!")
        return index
    
    # Save the index
    index_path = data_dir / "index"
    saved_path = index.save(index_path, compress=True)
    
    print(f"\n✅ Index complete!")
    print(f"   Documents indexed: {num_docs}")
    print(f"   Unique terms: {len(index.index)}")
    print(f"   Index saved to: {saved_path}")
    print(f"   Index size: {format_size(saved_path.stat().st_size)}")
    
    return index


def search_index(data_dir: Path, queries: list) -> None:
    """
    Stage 3: Search the index.
    
    Args:
        data_dir: Directory containing the index
        queries: List of search queries to test
    """
    print("\n" + "=" * 60)
    print("STAGE 3: SEARCHING")
    print("=" * 60)
    
    # Find the index file
    index_path = data_dir / "index.json.gz"
    if not index_path.exists():
        index_path = data_dir / "index.json"
    
    if not index_path.exists():
        raise FileNotFoundError(f"No index found at {data_dir}")
    
    print(f"\n📂 Loading index from: {index_path}")
    
    # Load enhanced search engine for full features
    engine = EnhancedSearchEngine.load(
        index_path,
        enable_spellcheck=True,
        enable_autocomplete=True,
        enable_facets=True,
    )
    
    stats = engine.get_stats()
    print(f"   Loaded {stats['total_documents']} documents")
    
    # =========================================================================
    # Run Searches
    # =========================================================================
    
    for query in queries:
        print(f"\n🔍 Query: '{query}'")
        print("-" * 40)
        
        # Use search_enhanced for full metadata
        response = engine.search_enhanced(query, top_k=5)
        
        results = response['results']
        
        if not results:
            print("   No results found.")
            continue
        
        # Show spelling suggestion if any
        if response.get('suggestion'):
            print(f"   💡 Did you mean: '{response['suggestion']}'")
        
        print(f"   Found {len(results)} results:\n")
        
        for i, result in enumerate(results[:3], 1):  # Show top 3
            title = result.get('title') or result.get('url', 'Unknown')
            print(f"   {i}. {title}")
            print(f"      URL: {result['url']}")
            print(f"      Score: {result['score']:.4f}")
            
            if result.get('snippet'):
                # Clean up snippet for display
                snippet = result['snippet']
                snippet = snippet.replace('<mark>', '').replace('</mark>', '')
                if len(snippet) > 80:
                    snippet = snippet[:80] + "..."
                print(f"      Preview: {snippet}")
            print()
    
    # =========================================================================
    # Show Autocomplete Demo
    # =========================================================================
    
    print("\n⌨️  Autocomplete Demo:")
    print("-" * 40)
    
    prefixes = ["http", "get", "api"]
    for prefix in prefixes:
        suggestions = engine.get_suggestions(prefix, max_suggestions=3)
        if suggestions:
            print(f"   '{prefix}' → {suggestions}")
        else:
            print(f"   '{prefix}' → (no suggestions)")


def main():
    """Run the full pipeline demo."""
    print("=" * 60)
    print("doc-search: Full Pipeline Demo")
    print("=" * 60)
    print("\nThis demo will:")
    print("  1. Crawl a small test site (httpbin.org)")
    print("  2. Build a search index")
    print("  3. Perform test searches")
    print("\nAll data is stored in a temporary directory and cleaned up after.")
    
    # =========================================================================
    # Configuration
    # =========================================================================
    
    # Use httpbin.org as a safe, predictable test target
    base_url = "https://httpbin.org"
    
    # Limit to a small number of pages for this demo
    max_pages = 5
    
    # Queries to test
    test_queries = [
        "http",           # Simple single-word query
        "request response",  # Multi-word query
        "api",            # Short query
    ]
    
    # =========================================================================
    # Run the Pipeline
    # =========================================================================
    
    # Use a temporary directory (cleaned up automatically)
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        
        try:
            # Stage 1: Crawl
            crawl_stats = crawl_site(base_url, data_dir, max_pages=max_pages)
            
            # Check if we got any pages
            pages_dir = data_dir / "pages"
            if not pages_dir.exists() or not any(pages_dir.iterdir()):
                print("\n⚠️ No pages were crawled. The site may be blocking our requests.")
                print("   Try with a different site or check your network connection.")
                return
            
            # Stage 2: Index
            index = build_index(data_dir)
            
            if index.total_docs == 0:
                print("\n⚠️ No documents were indexed.")
                return
            
            # Stage 3: Search
            search_index(data_dir, test_queries)
            
        except KeyboardInterrupt:
            print("\n\n⚠️ Interrupted by user")
            return
        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise
    
    # =========================================================================
    # Summary
    # =========================================================================
    
    print("\n" + "=" * 60)
    print("Pipeline Complete!")
    print("=" * 60)
    print("\n✅ Successfully demonstrated:")
    print("   • Web crawling with rate limiting")
    print("   • BM25 index building")
    print("   • Full-text search with relevance ranking")
    print("   • Autocomplete suggestions")
    
    print("\n📚 To use doc-search with your own documentation site:")
    print(f"   python -m doc_search crawl https://your-docs-site.com")
    print(f"   python -m doc_search index https://your-docs-site.com")
    print(f"   python -m doc_search serve https://your-docs-site.com --open")


if __name__ == "__main__":
    main()
