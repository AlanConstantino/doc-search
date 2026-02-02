"""
Performance benchmark tests for doc-search.

These tests measure and track performance of critical paths:
- CrawlState.add_urls() with large URL sets
- Index building time for various document counts
- Search query time on large indexes

Run benchmarks explicitly with:
    python -m pytest tests/test_benchmarks.py -v -m benchmark

Skip benchmarks during normal test runs:
    python -m pytest tests/ -m "not benchmark"
"""

import gc
import statistics
import tempfile
import time
import tracemalloc
import unittest
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import pytest

from doc_search.crawl_state import CrawlState
from doc_search.indexer import BM25Index
from doc_search.searcher import SearchEngine


# Mark all tests in this module as benchmarks
pytestmark = pytest.mark.benchmark


class BenchmarkResult:
    """Container for benchmark results with statistics."""
    
    def __init__(self, name: str, times: List[float], memory_mb: float = 0.0):
        self.name = name
        self.times = times
        self.memory_mb = memory_mb
    
    @property
    def min_time(self) -> float:
        return min(self.times)
    
    @property
    def max_time(self) -> float:
        return max(self.times)
    
    @property
    def mean_time(self) -> float:
        return statistics.mean(self.times)
    
    @property
    def median_time(self) -> float:
        return statistics.median(self.times)
    
    @property
    def stdev_time(self) -> float:
        return statistics.stdev(self.times) if len(self.times) > 1 else 0.0
    
    def __str__(self) -> str:
        return (
            f"{self.name}:\n"
            f"  Mean: {self.mean_time*1000:.2f}ms\n"
            f"  Median: {self.median_time*1000:.2f}ms\n"
            f"  Min: {self.min_time*1000:.2f}ms\n"
            f"  Max: {self.max_time*1000:.2f}ms\n"
            f"  StdDev: {self.stdev_time*1000:.2f}ms\n"
            f"  Memory: {self.memory_mb:.2f}MB"
        )


def run_benchmark(
    name: str,
    func: Callable,
    iterations: int = 5,
    warmup: int = 1,
    measure_memory: bool = False
) -> BenchmarkResult:
    """
    Run a benchmark function multiple times and collect timing statistics.
    
    Args:
        name: Benchmark name for reporting
        func: Function to benchmark (no arguments)
        iterations: Number of timed iterations
        warmup: Number of warmup iterations (not timed)
        measure_memory: Whether to measure peak memory usage
    
    Returns:
        BenchmarkResult with timing statistics
    """
    # Warmup runs
    for _ in range(warmup):
        func()
        gc.collect()
    
    times = []
    memory_mb = 0.0
    
    # Measure memory on first timed run if requested
    if measure_memory:
        gc.collect()
        tracemalloc.start()
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory_mb = peak / (1024 * 1024)
        times.append(end - start)
        iterations -= 1
    
    # Timed runs
    for _ in range(iterations):
        gc.collect()
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append(end - start)
    
    return BenchmarkResult(name, times, memory_mb)


def generate_urls(count: int, base: str = "https://example.com") -> List[Tuple[str, int]]:
    """Generate a list of test URLs with depths."""
    return [(f"{base}/page/{i}", i % 5) for i in range(count)]


def generate_documents(count: int) -> List[Dict]:
    """Generate test documents with realistic content."""
    # Sample content to make documents somewhat realistic
    words = [
        "python", "programming", "tutorial", "guide", "example",
        "function", "class", "module", "package", "import",
        "data", "structure", "algorithm", "search", "index",
        "documentation", "reference", "api", "library", "framework",
        "test", "debug", "error", "exception", "handling",
        "file", "read", "write", "process", "memory",
        "string", "list", "dict", "set", "tuple",
        "async", "await", "thread", "concurrent", "parallel"
    ]
    
    documents = []
    for i in range(count):
        # Generate pseudo-random but deterministic content
        title_words = [words[(i + j) % len(words)] for j in range(3)]
        # More text content for realistic document size
        text_words = [words[(i * 7 + j) % len(words)] for j in range(100)]
        
        documents.append({
            'doc_id': i,
            'url': f'https://example.com/doc/{i}',
            'title': ' '.join(title_words),
            'text': ' '.join(text_words),
            'description': f'Document {i} about {title_words[0]}'
        })
    
    return documents


class TestCrawlStateBenchmarks(unittest.TestCase):
    """Benchmarks for CrawlState operations."""
    
    def setUp(self):
        """Create a temporary state file for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / 'crawl_state.json'
    
    def tearDown(self):
        """Clean up temporary files."""
        if self.state_file.exists():
            self.state_file.unlink()
        Path(self.temp_dir).rmdir()
    
    def test_add_urls_small(self):
        """Benchmark add_urls with 1,000 URLs."""
        urls = generate_urls(1000)
        
        def benchmark():
            state = CrawlState(self.state_file)
            state.add_urls(urls)
        
        result = run_benchmark("CrawlState.add_urls (1K URLs)", benchmark, measure_memory=True)
        print(f"\n{result}")
        
        # Performance assertions - should complete in reasonable time
        self.assertLess(result.mean_time, 0.5, "add_urls(1K) should complete in <500ms")
    
    def test_add_urls_medium(self):
        """Benchmark add_urls with 10,000 URLs."""
        urls = generate_urls(10000)
        
        def benchmark():
            state = CrawlState(self.state_file)
            state.add_urls(urls)
        
        result = run_benchmark("CrawlState.add_urls (10K URLs)", benchmark, measure_memory=True)
        print(f"\n{result}")
        
        # Performance assertions
        self.assertLess(result.mean_time, 2.0, "add_urls(10K) should complete in <2s")
    
    def test_add_urls_large(self):
        """Benchmark add_urls with 100,000 URLs."""
        urls = generate_urls(100000)
        
        def benchmark():
            state = CrawlState(self.state_file)
            state.add_urls(urls)
        
        result = run_benchmark("CrawlState.add_urls (100K URLs)", benchmark, iterations=3, measure_memory=True)
        print(f"\n{result}")
        
        # Performance assertions
        self.assertLess(result.mean_time, 10.0, "add_urls(100K) should complete in <10s")
    
    def test_add_urls_with_duplicates(self):
        """Benchmark add_urls when many URLs are already visited."""
        urls = generate_urls(10000)
        
        def benchmark():
            state = CrawlState(self.state_file)
            # Pre-populate visited set
            for url, _ in urls[:5000]:
                state.visited.add(url)
            state.add_urls(urls)
        
        result = run_benchmark("CrawlState.add_urls (10K with 5K duplicates)", benchmark)
        print(f"\n{result}")
        
        # Should still be fast with duplicate filtering
        self.assertLess(result.mean_time, 2.0, "add_urls with duplicates should complete in <2s")


class TestIndexerBenchmarks(unittest.TestCase):
    """Benchmarks for BM25Index operations."""
    
    def test_index_small(self):
        """Benchmark indexing 100 documents."""
        documents = generate_documents(100)
        
        def benchmark():
            index = BM25Index()
            for doc in documents:
                index.add_document(
                    doc['doc_id'],
                    doc['url'],
                    doc['title'],
                    doc['text'],
                    doc['description']
                )
        
        result = run_benchmark("BM25Index.add_document (100 docs)", benchmark, measure_memory=True)
        print(f"\n{result}")
        
        # Performance assertion
        self.assertLess(result.mean_time, 1.0, "Indexing 100 docs should complete in <1s")
    
    def test_index_medium(self):
        """Benchmark indexing 1,000 documents."""
        documents = generate_documents(1000)
        
        def benchmark():
            index = BM25Index()
            for doc in documents:
                index.add_document(
                    doc['doc_id'],
                    doc['url'],
                    doc['title'],
                    doc['text'],
                    doc['description']
                )
        
        result = run_benchmark("BM25Index.add_document (1K docs)", benchmark, measure_memory=True)
        print(f"\n{result}")
        
        # Performance assertion
        self.assertLess(result.mean_time, 5.0, "Indexing 1K docs should complete in <5s")
    
    def test_index_large(self):
        """Benchmark indexing 5,000 documents."""
        documents = generate_documents(5000)
        
        def benchmark():
            index = BM25Index()
            for doc in documents:
                index.add_document(
                    doc['doc_id'],
                    doc['url'],
                    doc['title'],
                    doc['text'],
                    doc['description']
                )
        
        result = run_benchmark("BM25Index.add_document (5K docs)", benchmark, iterations=3, measure_memory=True)
        print(f"\n{result}")
        
        # Performance assertion - 5K docs with 100 words each
        self.assertLess(result.mean_time, 30.0, "Indexing 5K docs should complete in <30s")
    
    def test_index_throughput(self):
        """Measure indexing throughput (documents per second)."""
        documents = generate_documents(1000)
        
        index = BM25Index()
        start = time.perf_counter()
        for doc in documents:
            index.add_document(
                doc['doc_id'],
                doc['url'],
                doc['title'],
                doc['text'],
                doc['description']
            )
        elapsed = time.perf_counter() - start
        
        throughput = len(documents) / elapsed
        print(f"\nIndexing throughput: {throughput:.1f} docs/sec")
        
        # Should handle at least 100 docs/sec
        self.assertGreater(throughput, 100, "Indexing throughput should be >100 docs/sec")


class TestSearchBenchmarks(unittest.TestCase):
    """Benchmarks for search operations."""
    
    @classmethod
    def setUpClass(cls):
        """Build a test index once for all search benchmarks."""
        cls.documents = generate_documents(1000)
        cls.index = BM25Index()
        for doc in cls.documents:
            cls.index.add_document(
                doc['doc_id'],
                doc['url'],
                doc['title'],
                doc['text'],
                doc['description']
            )
        cls.engine = SearchEngine(cls.index)
    
    def test_search_simple_term(self):
        """Benchmark simple single-term search."""
        def benchmark():
            self.engine.search("python")
        
        result = run_benchmark("SearchEngine.search (single term)", benchmark, iterations=10)
        print(f"\n{result}")
        
        # Search should be fast
        self.assertLess(result.mean_time, 0.1, "Single term search should complete in <100ms")
    
    def test_search_multiple_terms(self):
        """Benchmark multi-term search."""
        def benchmark():
            self.engine.search("python programming tutorial")
        
        result = run_benchmark("SearchEngine.search (3 terms)", benchmark, iterations=10)
        print(f"\n{result}")
        
        # Multi-term search should still be fast
        self.assertLess(result.mean_time, 0.2, "Multi-term search should complete in <200ms")
    
    def test_search_phrase(self):
        """Benchmark phrase search."""
        def benchmark():
            self.engine.search('"python programming"')
        
        result = run_benchmark("SearchEngine.search (phrase)", benchmark, iterations=10)
        print(f"\n{result}")
        
        # Phrase search may be slower but still reasonable
        self.assertLess(result.mean_time, 0.3, "Phrase search should complete in <300ms")
    
    def test_search_throughput(self):
        """Measure search throughput (queries per second)."""
        queries = [
            "python", "programming", "tutorial", "guide",
            "function class", "data structure", "search index",
            '"python programming"', "api reference"
        ]
        
        num_queries = 100
        start = time.perf_counter()
        for i in range(num_queries):
            query = queries[i % len(queries)]
            self.engine.search(query)
        elapsed = time.perf_counter() - start
        
        throughput = num_queries / elapsed
        print(f"\nSearch throughput: {throughput:.1f} queries/sec")
        
        # Should handle at least 50 queries/sec
        self.assertGreater(throughput, 50, "Search throughput should be >50 queries/sec")
    
    def test_search_with_top_k(self):
        """Benchmark search with result limiting."""
        def benchmark():
            self.engine.search("python", top_k=10)
        
        result = run_benchmark("SearchEngine.search (top_k=10)", benchmark, iterations=10)
        print(f"\n{result}")
        
        self.assertLess(result.mean_time, 0.1, "Limited search should complete in <100ms")


class TestMemoryBenchmarks(unittest.TestCase):
    """Memory usage benchmarks."""
    
    def test_index_memory_scaling(self):
        """Test how memory scales with document count."""
        doc_counts = [100, 500, 1000]
        memory_per_count = {}
        
        for count in doc_counts:
            gc.collect()
            tracemalloc.start()
            
            documents = generate_documents(count)
            index = BM25Index()
            for doc in documents:
                index.add_document(
                    doc['doc_id'],
                    doc['url'],
                    doc['title'],
                    doc['text'],
                    doc['description']
                )
            
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            
            memory_mb = peak / (1024 * 1024)
            memory_per_count[count] = memory_mb
            print(f"\nIndex memory ({count} docs): {memory_mb:.2f} MB")
        
        # Check memory doesn't grow excessively (should be roughly linear)
        # Memory for 1000 docs should be less than 15x memory for 100 docs
        ratio = memory_per_count[1000] / memory_per_count[100]
        print(f"Memory ratio (1000/100 docs): {ratio:.1f}x")
        self.assertLess(ratio, 15, "Memory should scale reasonably with document count")


# Baseline performance numbers (updated 2024-02)
# These are reference values, not strict requirements
BASELINE_PERFORMANCE = """
Baseline Performance Numbers (reference):
=========================================
CrawlState.add_urls (1K URLs):   ~10-50ms
CrawlState.add_urls (10K URLs):  ~100-500ms
CrawlState.add_urls (100K URLs): ~1-5s

BM25Index (100 docs):  ~100-500ms
BM25Index (1K docs):   ~1-3s
BM25Index (5K docs):   ~5-15s
Indexing throughput:   ~200-500 docs/sec

Search (single term):  ~5-20ms
Search (3 terms):      ~10-50ms
Search (phrase):       ~20-100ms
Search throughput:     ~100-500 queries/sec

Index memory (100 docs):  ~1-5 MB
Index memory (1000 docs): ~5-20 MB
"""


if __name__ == '__main__':
    print(BASELINE_PERFORMANCE)
    print("\nRunning benchmarks...\n")
    unittest.main(verbosity=2)
