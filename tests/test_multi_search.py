"""Tests for multi-site search functionality."""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from doc_search.multi_search import (
    discover_sites,
    filter_sites,
    MultiSiteSearchEngine,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sites_dir(tmp_path):
    """Create a temporary sites directory with two indexed sites."""
    sites = tmp_path / "sites"
    sites.mkdir()
    
    # Create site A
    site_a = sites / "site_abc123"
    site_a.mkdir()
    pages_a = site_a / "pages"
    pages_a.mkdir()
    
    # Write metadata
    (site_a / "metadata.json").write_text(json.dumps({
        "url": "https://docs.example.com",
        "stats": {"pages_crawled": 3}
    }))
    
    # Write page files
    for i, (title, text) in enumerate([
        ("Python Lists", "Python lists are ordered mutable sequences used for storing collections"),
        ("Python Dicts", "Python dictionaries are key-value mappings for fast lookup"),
        ("Python Sets", "Python sets are unordered collections of unique elements"),
    ]):
        (pages_a / f"page_{i}.json").write_text(json.dumps({
            "url": f"https://docs.example.com/page{i}",
            "title": title,
            "text": text,
        }))
    
    # Create site B
    site_b = sites / "site_def456"
    site_b.mkdir()
    pages_b = site_b / "pages"
    pages_b.mkdir()
    
    (site_b / "metadata.json").write_text(json.dumps({
        "url": "https://wiki.example.org",
        "stats": {"pages_crawled": 2}
    }))
    
    for i, (title, text) in enumerate([
        ("JavaScript Arrays", "JavaScript arrays are ordered lists of values with many methods"),
        ("JavaScript Objects", "JavaScript objects are collections of key-value pairs"),
    ]):
        (pages_b / f"page_{i}.json").write_text(json.dumps({
            "url": f"https://wiki.example.org/page{i}",
            "title": title,
            "text": text,
        }))
    
    # Build indexes for both sites
    from doc_search.indexer import BM25Index
    
    for site_path in [site_a, site_b]:
        index = BM25Index()
        index.build_from_pages(site_path / "pages", verbose=False)
        index.save(site_path / "index.json", compress=False)
    
    return sites


@pytest.fixture
def empty_sites_dir(tmp_path):
    """Create an empty sites directory."""
    sites = tmp_path / "sites"
    sites.mkdir()
    return sites


# ============================================================================
# discover_sites tests
# ============================================================================

class TestDiscoverSites:
    def test_discover_finds_indexed_sites(self, sites_dir):
        sites = discover_sites(sites_dir)
        assert len(sites) == 2
    
    def test_discover_returns_site_info(self, sites_dir):
        sites = discover_sites(sites_dir)
        urls = {s['url'] for s in sites}
        assert "https://docs.example.com" in urls
        assert "https://wiki.example.org" in urls
    
    def test_discover_includes_index_path(self, sites_dir):
        sites = discover_sites(sites_dir)
        for site in sites:
            assert site['index_path'].exists()
    
    def test_discover_empty_dir(self, empty_sites_dir):
        sites = discover_sites(empty_sites_dir)
        assert sites == []
    
    def test_discover_nonexistent_dir(self, tmp_path):
        sites = discover_sites(tmp_path / "nonexistent")
        assert sites == []
    
    def test_discover_skips_dirs_without_index(self, sites_dir):
        # Add a site without an index
        no_index = sites_dir / "site_noindex"
        no_index.mkdir()
        (no_index / "metadata.json").write_text(json.dumps({"url": "https://no-index.com"}))
        
        sites = discover_sites(sites_dir)
        assert len(sites) == 2  # Only the two indexed sites
    
    def test_discover_handles_bad_metadata(self, sites_dir):
        # Corrupt one metadata file
        site = list(sites_dir.iterdir())[0]
        (site / "metadata.json").write_text("not json")
        
        sites = discover_sites(sites_dir)
        assert len(sites) == 2  # Still discovers it (just with default name)


# ============================================================================
# filter_sites tests
# ============================================================================

class TestFilterSites:
    def test_no_filter_returns_all(self, sites_dir):
        sites = discover_sites(sites_dir)
        filtered = filter_sites(sites, None)
        assert len(filtered) == 2
    
    def test_filter_by_url_substring(self, sites_dir):
        sites = discover_sites(sites_dir)
        filtered = filter_sites(sites, ["docs.example"])
        assert len(filtered) == 1
        assert filtered[0]['url'] == "https://docs.example.com"
    
    def test_filter_by_hash_prefix(self, sites_dir):
        sites = discover_sites(sites_dir)
        filtered = filter_sites(sites, ["site_abc"])
        assert len(filtered) == 1
        assert "abc123" in filtered[0]['hash']
    
    def test_filter_by_name(self, sites_dir):
        sites = discover_sites(sites_dir)
        filtered = filter_sites(sites, ["wiki"])
        assert len(filtered) == 1
    
    def test_filter_multiple_matches(self, sites_dir):
        sites = discover_sites(sites_dir)
        filtered = filter_sites(sites, ["example"])
        assert len(filtered) == 2
    
    def test_filter_no_match(self, sites_dir):
        sites = discover_sites(sites_dir)
        filtered = filter_sites(sites, ["nonexistent"])
        assert len(filtered) == 0
    
    def test_filter_case_insensitive(self, sites_dir):
        sites = discover_sites(sites_dir)
        filtered = filter_sites(sites, ["DOCS.EXAMPLE"])
        assert len(filtered) == 1


# ============================================================================
# MultiSiteSearchEngine tests
# ============================================================================

class TestMultiSiteSearchEngine:
    def test_init_discovers_sites(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        assert engine.site_count == 2
    
    def test_init_with_filters(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir, site_filters=["docs.example"])
        assert engine.site_count == 1
    
    def test_search_returns_results(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        results = engine.search("python", top_k=10)
        assert len(results) > 0
    
    def test_search_results_have_site_field(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        results = engine.search("python", top_k=10)
        for r in results:
            assert 'site' in r
            assert 'site_hash' in r
    
    def test_search_results_from_correct_site(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        results = engine.search("python lists", top_k=5)
        assert any("docs.example.com" in r.get('site', '') for r in results)
    
    def test_search_results_sorted_by_score(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        results = engine.search("collections", top_k=10)
        scores = [r['score'] for r in results]
        assert scores == sorted(scores, reverse=True)
    
    def test_search_limit(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        results = engine.search("python", top_k=2)
        assert len(results) <= 2
    
    def test_search_no_results(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        results = engine.search("xyznonexistentterm", top_k=10)
        assert results == []
    
    def test_search_across_multiple_sites(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        # "collections" appears in both sites
        results = engine.search("collections", top_k=10)
        sites_found = {r.get('site_hash') for r in results}
        # Should have results from at least one site
        assert len(sites_found) >= 1
    
    def test_search_enhanced(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        response = engine.search_enhanced("python", top_k=5)
        assert 'results' in response
        assert 'query' in response
        assert response['query'] == "python"
        assert 'sites_searched' in response
        assert response['sites_searched'] == 2
        assert 'site_names' in response
    
    def test_get_stats(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        stats = engine.get_stats()
        assert stats['total_sites'] == 2
        assert stats['total_documents'] == 5  # 3 + 2
        assert len(stats['sites']) == 2
    
    def test_sites_property(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        sites = engine.sites
        assert len(sites) == 2
        # Should be a copy
        sites.append({"fake": True})
        assert engine.site_count == 2
    
    def test_empty_sites(self, empty_sites_dir):
        engine = MultiSiteSearchEngine(data_dir=empty_sites_dir)
        assert engine.site_count == 0
        results = engine.search("anything")
        assert results == []
    
    def test_compatibility_methods(self, sites_dir):
        """Test server-compatibility stub methods."""
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        assert engine.last_suggestion is None
        assert engine.get_spelling_suggestion("test") is None
        # title suggestions handled by TitleSuggester (not available on MultiSiteSearchEngine)
        assert engine.get_facet_counts() == {}
    
    def test_search_with_site_filter(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir, site_filters=["wiki"])
        results = engine.search("javascript", top_k=10)
        for r in results:
            assert "wiki.example.org" in r.get('site', '')


# ============================================================================
# CLI integration tests
# ============================================================================

class TestSearchAllCLI:
    def test_search_all_no_sites(self, empty_sites_dir):
        """search-all with no indexed sites should return error."""
        from doc_search.cli.commands import cmd_search_all
        
        args = MagicMock()
        args.query = "python"
        args.limit = 10
        args.sites = None
        args.scores = False
        args.json = False
        args.quiet = False
        args.no_color = False
        
        with patch('doc_search.multi_search.DEFAULT_DATA_DIR', empty_sites_dir):
            result = cmd_search_all(args)
        assert result == 1
    
    def test_search_all_json_output(self, sites_dir):
        """search-all --json should produce valid JSON."""
        from doc_search.cli.commands import cmd_search_all
        
        args = MagicMock()
        args.query = "python"
        args.limit = 5
        args.sites = None
        args.scores = False
        args.json = True
        args.quiet = True
        args.no_color = False
        
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        with patch('doc_search.multi_search.DEFAULT_DATA_DIR', sites_dir):
            with redirect_stdout(f):
                result = cmd_search_all(args)
        
        assert result == 0
        output = json.loads(f.getvalue())
        assert output['query'] == "python"
        assert 'results' in output
        assert 'sites_searched' in output
    
    def test_search_all_with_site_filter(self, sites_dir):
        """search-all --sites should filter results."""
        from doc_search.cli.commands import cmd_search_all
        
        args = MagicMock()
        args.query = "collections"
        args.limit = 10
        args.sites = ["docs.example"]
        args.scores = False
        args.json = True
        args.quiet = True
        args.no_color = False
        
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        with patch('doc_search.multi_search.DEFAULT_DATA_DIR', sites_dir):
            with redirect_stdout(f):
                result = cmd_search_all(args)
        
        assert result == 0
        output = json.loads(f.getvalue())
        assert output['sites_searched'] == 1


class TestServeAllFlag:
    def test_serve_requires_site_dir_or_all(self):
        """serve without site_dir or --all should error."""
        from doc_search.cli.commands import cmd_serve
        
        args = MagicMock()
        args.all = False
        args.site_dir = None
        args.separate_paths = False
        
        result = cmd_serve(args)
        assert result == 1
    
    def test_serve_all_no_sites(self, empty_sites_dir):
        """serve --all with no indexed sites should error."""
        from doc_search.cli.commands import cmd_serve
        
        args = MagicMock()
        args.all = True
        args.sites = None
        
        with patch('doc_search.multi_search.DEFAULT_DATA_DIR', empty_sites_dir):
            result = cmd_serve(args)
        assert result == 1


# ============================================================================
# Edge case tests
# ============================================================================

class TestMultiSiteEdgeCases:
    def test_site_with_corrupt_index(self, sites_dir):
        """Sites with corrupt indexes should be skipped gracefully."""
        # Corrupt one index
        for idx_file in (sites_dir / "site_abc123").glob("index.*"):
            idx_file.write_text("corrupt data")
        
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        # Should still work with the remaining site
        results = engine.search("javascript", top_k=10)
        # Results should come from the working site only
        for r in results:
            assert "wiki.example.org" in r.get('site', '')
    
    def test_search_merges_across_sites(self, sites_dir):
        """Results from different sites should be properly merged."""
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        # "ordered" appears in both sites (lists/arrays descriptions)
        results = engine.search("ordered", top_k=10)
        # Verify scores are properly merged (descending)
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i]['score'] >= results[i+1]['score']
    
    def test_pre_supplied_sites_list(self, sites_dir):
        """Test passing pre-discovered sites list."""
        sites = discover_sites(sites_dir)
        engine = MultiSiteSearchEngine(sites=sites[:1])  # Only first site
        assert engine.site_count == 1
    
    def test_highlight_in_results(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        results = engine.search("python", top_k=5, highlight=True)
        # Results should be returned (highlighting doesn't break anything)
        assert isinstance(results, list)
    
    def test_search_with_phrases(self, sites_dir):
        engine = MultiSiteSearchEngine(data_dir=sites_dir)
        results = engine.search('"key-value"', top_k=5)
        # Should not error
        assert isinstance(results, list)
