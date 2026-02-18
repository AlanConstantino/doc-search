"""Tests for file preview improvements: URL rewriting and text normalization."""
import unittest
from doc_search.searcher_utils import normalize_document_text


class TestNormalizeDocumentText(unittest.TestCase):
    """Test text normalization for PDF/Word extracted text."""

    def test_empty_text(self):
        self.assertEqual(normalize_document_text(''), '')
        self.assertEqual(normalize_document_text(None), None)

    def test_clean_text_unchanged(self):
        text = "This is a clean sentence."
        self.assertEqual(normalize_document_text(text), text)

    def test_joins_broken_lines(self):
        text = "this is a broken\nsentence that continues"
        result = normalize_document_text(text)
        self.assertEqual(result, "this is a broken sentence that continues")

    def test_preserves_paragraph_breaks(self):
        text = "First paragraph.\n\nSecond paragraph."
        result = normalize_document_text(text)
        self.assertIn('\n\n', result)
        self.assertIn('First paragraph.', result)
        self.assertIn('Second paragraph.', result)

    def test_joins_capitalized_new_lines(self):
        """Single newlines are joined even between sentences (PDF artifact)."""
        text = "End of sentence.\nStart of new sentence."
        result = normalize_document_text(text)
        self.assertEqual(result, "End of sentence. Start of new sentence.")

    def test_collapses_excessive_whitespace(self):
        text = "too   many    spaces"
        result = normalize_document_text(text)
        self.assertEqual(result, "too many spaces")

    def test_collapses_excessive_newlines(self):
        text = "para one\n\n\n\n\npara two"
        result = normalize_document_text(text)
        self.assertEqual(result, "para one\n\npara two")

    def test_removes_soft_hyphens(self):
        text = "docu\xadment"
        result = normalize_document_text(text)
        self.assertEqual(result, "document")

    def test_normalizes_unicode_whitespace(self):
        text = "non\xa0breaking\u2003space"
        result = normalize_document_text(text)
        self.assertEqual(result, "non breaking space")

    def test_joins_hyphenated_line_break(self):
        text = "this line is hyphen-\nated here"
        result = normalize_document_text(text)
        self.assertEqual(result, "this line is hyphen- ated here")

    def test_mid_sentence_comma_continuation(self):
        text = "first item,\nsecond item"
        result = normalize_document_text(text)
        self.assertEqual(result, "first item, second item")


class TestFileUrlToServeUrl(unittest.TestCase):
    """Test file:// URL to /files/ URL conversion."""

    def test_file_url_conversion(self):
        from doc_search.server import SearchHandler
        url = "file:///Users/test/docs/report.pdf"
        result = SearchHandler.file_url_to_serve_url(url)
        self.assertEqual(result, "/files//Users/test/docs/report.pdf")

    def test_file_url_with_fragment(self):
        from doc_search.server import SearchHandler
        url = "file:///Users/test/docs/report.pdf#page=3"
        result = SearchHandler.file_url_to_serve_url(url)
        self.assertEqual(result, "/files//Users/test/docs/report.pdf#page=3")

    def test_http_url_unchanged(self):
        from doc_search.server import SearchHandler
        url = "https://example.com/page"
        result = SearchHandler.file_url_to_serve_url(url)
        self.assertEqual(result, url)

    def test_spaces_in_path(self):
        from doc_search.server import SearchHandler
        url = "file:///Users/test/my docs/report.pdf"
        result = SearchHandler.file_url_to_serve_url(url)
        self.assertIn("/files/", result)
        self.assertIn("my%20docs", result)


if __name__ == '__main__':
    unittest.main()
