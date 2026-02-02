#!/usr/bin/env python3
"""
Profile hot paths in doc-search to identify optimization opportunities.

This script profiles:
1. Indexing (BM25Index.add_document)
2. Searching (SearchEngine.search, EnhancedSearchEngine.search)
3. Tokenization (tokenize function)

Run: python scripts/profile_hotpaths.py
"""

import cProfile
import pstats
import io
import time
import random
import string
from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from doc_search.indexer import BM25Index
from doc_search.searcher import SearchEngine, EnhancedSearchEngine
from doc_search.utils import tokenize
from doc_search.stemmer import stem


def generate_random_text(words: int = 500) -> str:
    """Generate random text with realistic word distribution."""
    common_words = [
        "python", "programming", "function", "class", "method", "variable",
        "string", "list", "dictionary", "tuple", "set", "loop", "condition",
        "import", "module", "package", "file", "data", "object", "type",
        "integer", "float", "boolean", "none", "true", "false", "return",
        "exception", "error", "try", "except", "finally", "with", "as",
        "lambda", "generator", "iterator", "decorator", "context", "manager",
        "async", "await", "coroutine", "thread", "process", "memory", "cpu",
        "algorithm", "structure", "array", "queue", "stack", "tree", "graph",
        "search", "sort", "binary", "hash", "index", "key", "value", "pair",
        "documentation", "tutorial", "example", "guide", "reference", "api",
    ]
    return " ".join(random.choice(common_words) for _ in range(words))


def generate_random_title() -> str:
    """Generate a random title."""
    topics = ["Python", "JavaScript", "Data", "API", "Guide", "Tutorial", "Reference"]
    actions = ["Introduction", "Getting Started", "Advanced", "Best Practices", "Tips"]
    return f"{random.choice(topics)} {random.choice(actions)}"


def profile_tokenization(iterations: int = 10000):
    """Profile the tokenize function."""
    print("\n" + "="*60)
    print("PROFILING: Tokenization")
    print("="*60)
    
    # Generate test texts of varying sizes
    texts = [
        generate_random_text(100) for _ in range(100)
    ] + [
        generate_random_text(500) for _ in range(50)
    ] + [
        generate_random_text(1000) for _ in range(25)
    ]
    
    # Profile without stemming
    print(f"\nProfiling tokenize() without stemming ({iterations} iterations)...")
    profiler = cProfile.Profile()
    profiler.enable()
    
    for _ in range(iterations):
        text = random.choice(texts)
        tokenize(text, apply_stemming=False)
    
    profiler.disable()
    
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(20)
    print(s.getvalue())
    
    # Profile with stemming
    print(f"\nProfiling tokenize() with stemming ({iterations} iterations)...")
    profiler = cProfile.Profile()
    profiler.enable()
    
    for _ in range(iterations):
        text = random.choice(texts)
        tokenize(text, apply_stemming=True)
    
    profiler.disable()
    
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(20)
    print(s.getvalue())


def profile_indexing(num_docs: int = 1000):
    """Profile BM25Index.add_document."""
    print("\n" + "="*60)
    print("PROFILING: Indexing (BM25Index)")
    print("="*60)
    
    # Generate test documents
    docs = []
    for i in range(num_docs):
        docs.append({
            'doc_id': i,
            'url': f'https://example.com/docs/{i}',
            'title': generate_random_title(),
            'text': generate_random_text(random.randint(200, 800)),
            'description': generate_random_text(30),
            'headings': [(1, generate_random_title()), (2, generate_random_title())]
        })
    
    print(f"\nProfiling indexing of {num_docs} documents...")
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    index = BM25Index(stem=True)
    for doc in docs:
        index.add_document(
            doc_id=doc['doc_id'],
            url=doc['url'],
            title=doc['title'],
            text=doc['text'],
            description=doc['description'],
            headings=doc['headings']
        )
    
    profiler.disable()
    
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(30)
    print(s.getvalue())
    
    return index


def profile_searching(index: BM25Index, iterations: int = 1000):
    """Profile SearchEngine.search."""
    print("\n" + "="*60)
    print("PROFILING: Searching (SearchEngine)")
    print("="*60)
    
    engine = SearchEngine(index)
    
    # Generate test queries
    queries = [
        "python programming",
        "function class method",
        "data structure algorithm",
        "api reference documentation",
        "tutorial example guide",
        "async await coroutine",
        "\"python programming\"",  # phrase search
        "python \"data structure\"",  # mixed
    ]
    
    print(f"\nProfiling SearchEngine.search() ({iterations} iterations)...")
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    for _ in range(iterations):
        query = random.choice(queries)
        engine.search(query, top_k=10)
    
    profiler.disable()
    
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(30)
    print(s.getvalue())


def profile_enhanced_searching(index: BM25Index, iterations: int = 500):
    """Profile EnhancedSearchEngine.search."""
    print("\n" + "="*60)
    print("PROFILING: Enhanced Searching (EnhancedSearchEngine)")
    print("="*60)
    
    engine = EnhancedSearchEngine(
        index,
        enable_spellcheck=True,
        enable_autocomplete=True,
        enable_facets=True,
        enable_synonyms=True
    )
    
    # Generate test queries
    queries = [
        "python programming",
        "function class method",
        "data structure algorithm",
        "api reference documentation",
        "programing tutoral",  # misspelled
        "async await coroutine",
    ]
    
    print(f"\nProfiling EnhancedSearchEngine.search() ({iterations} iterations)...")
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    for _ in range(iterations):
        query = random.choice(queries)
        engine.search(query, top_k=10, expand_synonyms=True)
    
    profiler.disable()
    
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(30)
    print(s.getvalue())


def profile_stemmer(iterations: int = 50000):
    """Profile the stemmer function."""
    print("\n" + "="*60)
    print("PROFILING: Porter Stemmer")
    print("="*60)
    
    # Common words to stem
    words = [
        "running", "files", "caresses", "programming", "functions",
        "algorithms", "documentation", "structures", "implementation",
        "optimization", "performance", "searching", "indexing", "crawling",
        "processing", "generating", "computing", "developing", "testing",
        "debugging", "deploying", "monitoring", "logging", "handling",
    ]
    
    print(f"\nProfiling stem() ({iterations} iterations)...")
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    for _ in range(iterations):
        word = random.choice(words)
        stem(word)
    
    profiler.disable()
    
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(20)
    print(s.getvalue())


def benchmark_comparison():
    """Run benchmarks to measure absolute performance."""
    print("\n" + "="*60)
    print("BENCHMARK: Performance Measurements")
    print("="*60)
    
    # Tokenization benchmark
    text = generate_random_text(500)
    iterations = 10000
    
    start = time.perf_counter()
    for _ in range(iterations):
        tokenize(text, apply_stemming=False)
    no_stem_time = time.perf_counter() - start
    
    start = time.perf_counter()
    for _ in range(iterations):
        tokenize(text, apply_stemming=True)
    stem_time = time.perf_counter() - start
    
    print(f"\nTokenization ({iterations} iterations, 500-word text):")
    print(f"  Without stemming: {no_stem_time:.3f}s ({no_stem_time/iterations*1000:.3f}ms/call)")
    print(f"  With stemming:    {stem_time:.3f}s ({stem_time/iterations*1000:.3f}ms/call)")
    
    # Indexing benchmark
    index = BM25Index(stem=True)
    docs = [
        {
            'doc_id': i,
            'url': f'https://example.com/{i}',
            'title': generate_random_title(),
            'text': generate_random_text(500),
            'description': generate_random_text(30),
            'headings': [(1, "Heading")]
        }
        for i in range(100)
    ]
    
    start = time.perf_counter()
    for doc in docs:
        index.add_document(**doc)
    index_time = time.perf_counter() - start
    
    print(f"\nIndexing (100 documents, ~500 words each):")
    print(f"  Total time: {index_time:.3f}s ({index_time/100*1000:.3f}ms/doc)")
    
    # Search benchmark
    engine = SearchEngine(index)
    queries = ["python programming", "function class", "data structure"]
    iterations = 1000
    
    start = time.perf_counter()
    for _ in range(iterations):
        engine.search(random.choice(queries), top_k=10)
    search_time = time.perf_counter() - start
    
    print(f"\nSearching ({iterations} queries):")
    print(f"  Total time: {search_time:.3f}s ({search_time/iterations*1000:.3f}ms/query)")


if __name__ == "__main__":
    print("="*60)
    print("DOC-SEARCH HOT PATH PROFILING")
    print("="*60)
    
    # Profile each component
    profile_tokenization(iterations=5000)
    profile_stemmer(iterations=50000)
    index = profile_indexing(num_docs=500)
    profile_searching(index, iterations=500)
    profile_enhanced_searching(index, iterations=200)
    
    # Run benchmarks
    benchmark_comparison()
    
    print("\n" + "="*60)
    print("PROFILING COMPLETE")
    print("="*60)
