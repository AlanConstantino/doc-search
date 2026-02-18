"""Tests for title-based suggestion engine."""

import json
import tempfile
from pathlib import Path

import pytest
from doc_search.title_suggester import TitleSuggester


class TestTitleSuggester:
    """Test basic title suggestion functionality."""

    def setup_method(self):
        self.suggester = TitleSuggester()
        self.suggester.add_page(
            "Getting Started with Python",
            "https://example.com/python",
            "html",
            [[1, "Installation"], [2, "First Steps"], [2, "Hello World"]],
        )
        self.suggester.add_page(
            "Algorithm Design Manual",
            "file:///docs/algo.pdf",
            "pdf",
            [[1, "Sorting Algorithms"], [2, "Graph Traversal"]],
        )
        self.suggester.add_page(
            "Excel Budget Template",
            "file:///docs/budget.xlsx",
            "xlsx",
        )

    def test_suggest_by_title_prefix(self):
        results = self.suggester.suggest("Getting")
        assert len(results) >= 1
        assert results[0]['text'] == "Getting Started with Python"

    def test_suggest_by_word_in_title(self):
        results = self.suggester.suggest("Python")
        assert any(r['text'] == "Getting Started with Python" for r in results)

    def test_suggest_by_heading(self):
        results = self.suggester.suggest("Sorting")
        assert any(r['text'] == "Sorting Algorithms" for r in results)

    def test_suggest_case_insensitive(self):
        results = self.suggester.suggest("algorithm")
        assert any(r['text'] == "Algorithm Design Manual" for r in results)

    def test_suggest_returns_doc_type(self):
        results = self.suggester.suggest("Algorithm")
        match = [r for r in results if r['text'] == "Algorithm Design Manual"]
        assert len(match) == 1
        assert match[0]['doc_type'] == 'pdf'

    def test_suggest_returns_url(self):
        results = self.suggester.suggest("Excel")
        match = [r for r in results if r['text'] == "Excel Budget Template"]
        assert len(match) == 1
        assert match[0]['url'] == "file:///docs/budget.xlsx"

    def test_suggest_empty_prefix(self):
        assert self.suggester.suggest("") == []

    def test_suggest_short_prefix(self):
        assert self.suggester.suggest("a") == []

    def test_suggest_no_match(self):
        assert self.suggester.suggest("zzzzz") == []

    def test_suggest_max_results(self):
        results = self.suggester.suggest("al", max_suggestions=1)
        assert len(results) <= 1

    def test_titles_ranked_above_headings(self):
        results = self.suggester.suggest("al")
        texts = [r['text'] for r in results]
        # "Algorithm Design Manual" (title) should come before headings
        if "Algorithm Design Manual" in texts:
            title_idx = texts.index("Algorithm Design Manual")
            for r in results[title_idx + 1:]:
                # Everything after title should have lower weight
                assert r['weight'] <= results[title_idx]['weight']

    def test_substring_match(self):
        results = self.suggester.suggest("Design")
        assert any(r['text'] == "Algorithm Design Manual" for r in results)

    def test_dedup_identical_titles(self):
        s = TitleSuggester()
        s.add_page("Hello World", "url1", "html")
        s.add_page("Hello World", "url2", "html")
        assert len(s.entries) == 1


class TestTitleSuggesterCleaning:
    """Test text cleaning for titles and headings."""

    def test_strips_pilcrow(self):
        s = TitleSuggester()
        s.add_page("Test", "url", "html", [[1, "Some Heading¶"]])
        assert any(e['text'] == "Some Heading" for e in s.entries)

    def test_strips_section_numbers(self):
        s = TitleSuggester()
        s.add_page("Test", "url", "html", [[1, "18.5.9. Develop with asyncio"]])
        assert any(e['text'] == "Develop with asyncio" for e in s.entries)

    def test_skips_navigation_headings(self):
        s = TitleSuggester()
        s.add_page("Test", "url", "html", [
            [1, "Navigation"],
            [2, "Table of Contents"],
            [2, "Previous Topic"],
        ])
        # Only the title should be added, not the nav headings
        heading_entries = [e for e in s.entries if e['weight'] < 100]
        assert len(heading_entries) == 0

    def test_skips_short_headings(self):
        s = TitleSuggester()
        s.add_page("Test Title", "url", "html", [[1, "Hi"]])
        heading_entries = [e for e in s.entries if e['weight'] < 100]
        assert len(heading_entries) == 0

    def test_skips_deep_headings(self):
        s = TitleSuggester()
        s.add_page("Test Title", "url", "html", [
            [1, "Good Heading"],
            [4, "Too Deep Heading"],
            [5, "Way Too Deep"],
        ])
        heading_entries = [e for e in s.entries if e['weight'] < 100]
        # Only h1 should be included (h4, h5 skipped)
        assert len(heading_entries) == 1
        assert heading_entries[0]['text'] == "Good Heading"


class TestTitleSuggesterPersistence:
    """Test save/load functionality."""

    def test_save_and_load_compressed(self):
        s = TitleSuggester()
        s.add_page("Python Tutorial", "url1", "html", [[1, "Basics"]])
        s.add_page("PDF Guide", "url2", "pdf")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = s.save(str(Path(tmpdir) / "titles"), compress=True)
            assert path.suffix == '.gz'

            loaded = TitleSuggester.load(str(path))
            assert len(loaded.entries) == len(s.entries)
            results = loaded.suggest("Python")
            assert len(results) >= 1
            assert results[0]['text'] == "Python Tutorial"

    def test_save_and_load_uncompressed(self):
        s = TitleSuggester()
        s.add_page("Test Page", "url", "html")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = s.save(str(Path(tmpdir) / "titles"), compress=False)
            assert path.suffix == '.json'

            loaded = TitleSuggester.load(str(path))
            assert len(loaded.entries) == 1

    def test_load_preserves_dedup(self):
        s = TitleSuggester()
        s.add_page("Unique Title", "url1", "html")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = s.save(str(Path(tmpdir) / "titles"))
            loaded = TitleSuggester.load(str(path))
            # Adding same title again should be deduped
            loaded.add_page("Unique Title", "url2", "html")
            assert len(loaded.entries) == 1


class TestTitleSuggesterBuildFromPages:
    """Test building from page JSON files."""

    def test_build_from_pages_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / "pages"
            pages_dir.mkdir()

            # Create sample page files
            page1 = {
                "title": "Python Documentation",
                "url": "https://docs.python.org",
                "doc_type": "html",
                "headings": [[1, "Library Reference"], [2, "Built-in Functions"]],
            }
            page2 = {
                "title": "Research Paper on AI",
                "url": "file:///paper.pdf",
                "doc_type": "pdf",
                "headings": [[1, "Abstract"], [2, "Methodology"]],
            }

            (pages_dir / "page1.json").write_text(json.dumps(page1))
            (pages_dir / "page2.json").write_text(json.dumps(page2))

            s = TitleSuggester()
            count = s.build_from_pages(pages_dir)
            assert count > 0
            assert len(s.entries) > 0

            # Should find titles
            results = s.suggest("Python")
            assert len(results) >= 1

            # Should find headings
            results = s.suggest("Methodology")
            assert len(results) >= 1

    def test_build_from_nonexistent_dir(self):
        s = TitleSuggester()
        count = s.build_from_pages(Path("/nonexistent"))
        assert count == 0

    def test_build_handles_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir)
            (pages_dir / "bad.json").write_text("{invalid json")
            (pages_dir / "good.json").write_text(json.dumps({
                "title": "Good Page", "url": "url", "headings": [],
            }))

            s = TitleSuggester()
            s.build_from_pages(pages_dir)
            # Should still have the good page
            assert len(s.entries) >= 1


class TestTitleSuggesterStats:
    """Test stats reporting."""

    def test_get_stats(self):
        s = TitleSuggester()
        s.add_page("Web Page", "url1", "html")
        s.add_page("PDF Doc", "url2", "pdf")
        s.add_page("Excel Sheet", "url3", "xlsx")

        stats = s.get_stats()
        assert stats['total_entries'] == 3
        assert stats['by_type']['html'] == 1
        assert stats['by_type']['pdf'] == 1
        assert stats['by_type']['xlsx'] == 1
