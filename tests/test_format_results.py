"""Tests for format_results type badges."""
import unittest
from doc_search.searcher_utils import format_results


class TestFormatResultsTypeBadges(unittest.TestCase):
    """Test that doc type badges appear for all document types."""

    def _make_result(self, doc_type='html', title='Test', url='https://example.com'):
        return {'title': title, 'url': url, 'score': 1.0, 'doc_type': doc_type, 'snippet': 'A snippet.'}

    def test_html_shows_web_badge(self):
        output = format_results([self._make_result('html')], colorize_output=False)
        self.assertIn('[WEB]', output)

    def test_pdf_shows_pdf_badge(self):
        output = format_results([self._make_result('pdf')], colorize_output=False)
        self.assertIn('[PDF]', output)

    def test_xlsx_shows_xlsx_badge(self):
        output = format_results([self._make_result('xlsx')], colorize_output=False)
        self.assertIn('[XLSX]', output)

    def test_docx_shows_docx_badge(self):
        output = format_results([self._make_result('docx')], colorize_output=False)
        self.assertIn('[DOCX]', output)

    def test_default_type_is_web(self):
        result = {'title': 'No Type', 'url': 'https://example.com', 'score': 1.0, 'snippet': 'test'}
        output = format_results([result], colorize_output=False)
        self.assertIn('[WEB]', output)

    def test_unknown_type_uppercased(self):
        output = format_results([self._make_result('csv')], colorize_output=False)
        self.assertIn('[CSV]', output)

    def test_badges_with_scores(self):
        output = format_results([self._make_result('pdf')], show_scores=True, colorize_output=False)
        self.assertIn('[PDF]', output)

    def test_colored_output_has_badges(self):
        output = format_results([self._make_result('pdf')], colorize_output=True)
        self.assertIn('[PDF]', output)

    def test_colored_web_badge(self):
        output = format_results([self._make_result('html')], colorize_output=True)
        self.assertIn('[WEB]', output)


if __name__ == '__main__':
    unittest.main()
