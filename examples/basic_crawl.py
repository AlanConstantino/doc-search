#!/usr/bin/env python3
"""
Basic Crawling Example

This example demonstrates how to use the Crawler class to crawl
a documentation site programmatically.

Run from repository root:
    python examples/basic_crawl.py

Note: This example crawls a real site (httpbin.org) but limits to 
just a few pages to keep it quick. For a full crawl of a documentation
site, remove the max_pages limit.
"""

import json
from pathlib import Path

# Import from doc_search package
from doc_search.crawl import Crawler
from doc_search.core import site_hash


def main():
    # =========================================================================
    # Configuration
    # =========================================================================
    
    # The URL to crawl (using httpbin.org as a safe test target)
    base_url = "https://httpbin.org"
    
    # Where to store crawled data
    # Default location is ~/.doc_search/sites/<site_hash>/
    data_dir = Path.home() / ".doc_search" / "sites" / site_hash(base_url)
    
    # Ensure directory exists
    data_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("doc-search: Basic Crawling Example")
    print("=" * 60)
    print(f"\nTarget URL: {base_url}")
    print(f"Data directory: {data_dir}")
    print()
    
    # =========================================================================
    # Create the Crawler
    # =========================================================================
    
    crawler = Crawler(
        base_url=base_url,
        data_dir=data_dir,
        
        # Rate limiting - be polite to the server
        delay=1.0,              # Wait 1 second between requests
        timeout=30.0,           # Request timeout in seconds
        
        # Crawl limits - useful for testing or partial crawls
        max_pages=5,            # Only crawl 5 pages for this demo
        max_depth=2,            # Maximum link depth from start URL
        
        # Parallelism - use with caution, always respect rate limits
        workers=1,              # Number of parallel workers
        
        # Content extraction
        extract_docs=False,     # Set True to extract text from PDFs
        
        # Output
        verbose=True,           # Print progress messages
    )
    
    # =========================================================================
    # Run the Crawl
    # =========================================================================
    
    print("Starting crawl...")
    print("-" * 60)
    
    # The crawl() method returns statistics about the crawl
    # resume=True continues an interrupted crawl from where it left off
    # resume=False starts fresh (clears existing state)
    stats = crawler.crawl(resume=False)
    
    print("-" * 60)
    print("\nCrawl complete!")
    
    # =========================================================================
    # Examine the Results
    # =========================================================================
    
    print("\n📊 Crawl Statistics:")
    print(f"  Pages crawled: {stats.get('pages_crawled', 0)}")
    print(f"  Pages skipped: {stats.get('pages_skipped', 0)}")
    print(f"  Errors: {stats.get('errors', 0)}")
    
    if 'duration' in stats:
        print(f"  Duration: {stats['duration']:.1f} seconds")
    
    # Check what was saved
    pages_dir = data_dir / "pages"
    if pages_dir.exists():
        page_files = list(pages_dir.glob("*.json"))
        print(f"\n📁 Saved {len(page_files)} page files to: {pages_dir}")
        
        # Show a sample of what was crawled
        if page_files:
            print("\n📄 Sample pages:")
            for page_file in page_files[:3]:
                with open(page_file) as f:
                    page_data = json.load(f)
                print(f"  - {page_data.get('title', 'No title')}")
                print(f"    URL: {page_data.get('url', 'Unknown')}")
    
    # =========================================================================
    # Save Metadata
    # =========================================================================
    
    # It's good practice to save metadata about the crawl
    metadata = {
        "url": base_url,
        "stats": stats,
    }
    
    metadata_path = data_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n✅ Metadata saved to: {metadata_path}")
    
    # =========================================================================
    # Next Steps
    # =========================================================================
    
    print("\n" + "=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print("1. Build an index:  python examples/build_index.py")
    print("2. Search the index: python examples/search_example.py")
    print("3. Or use the CLI:   python -m doc_search index", base_url)


if __name__ == "__main__":
    main()
