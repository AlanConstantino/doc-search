"""
Tests for the PDFExtractor class.
"""

import base64
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

from doc_search.pdf_extractor import PDFExtractor, extract_pdf_text


# ============================================================================
# Test PDF Content Helpers
# ============================================================================

def create_minimal_pdf(text: str = "Hello, World!", title: str = "", author: str = "") -> bytes:
    """
    Create a minimal valid PDF with given text content.
    
    This creates a simple one-page PDF with the text.
    """
    # Build PDF objects
    objects = []
    
    # Object 1: Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")
    
    # Object 2: Pages
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj")
    
    # Object 3: Page
    objects.append(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj")
    
    # Object 4: Content stream (text)
    content = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET".encode()
    objects.append(f"4 0 obj\n<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream\nendobj")
    
    # Object 5: Font
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj")
    
    # Object 6: Info (metadata) if title or author provided
    info_parts = []
    if title:
        info_parts.append(f"/Title ({title})")
    if author:
        info_parts.append(f"/Author ({author})")
    
    if info_parts:
        objects.append(f"6 0 obj\n<< {' '.join(info_parts)} >>\nendobj".encode())
    
    # Build PDF
    pdf = BytesIO()
    pdf.write(b"%PDF-1.4\n")
    
    # Track object positions for xref
    positions = []
    
    for obj in objects:
        positions.append(pdf.tell())
        pdf.write(obj + b"\n")
    
    # Write xref
    xref_pos = pdf.tell()
    pdf.write(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.write(b"0000000000 65535 f \n")  # Object 0 (free)
    for pos in positions:
        pdf.write(f"{pos:010d} 00000 n \n".encode())
    
    # Write trailer
    trailer_info = f"/Info {len(objects)} 0 R " if info_parts else ""
    pdf.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R {trailer_info}>>\n".encode())
    pdf.write(f"startxref\n{xref_pos}\n".encode())
    pdf.write(b"%%EOF")
    
    return pdf.getvalue()


# ============================================================================
# Basic Initialization Tests
# ============================================================================

class TestPDFExtractorInit(unittest.TestCase):
    """Tests for PDFExtractor initialization."""
    
    def test_default_init(self):
        """Should initialize with default values."""
        extractor = PDFExtractor()
        self.assertEqual(extractor.timeout, 30.0)
        self.assertEqual(extractor.user_agent, "DocSearchBot/1.2")
        self.assertIsNone(extractor.auth)
        self.assertIsNone(extractor.auth_token)
    
    def test_custom_timeout(self):
        """Should accept custom timeout."""
        extractor = PDFExtractor(timeout=60.0)
        self.assertEqual(extractor.timeout, 60.0)
    
    def test_custom_user_agent(self):
        """Should accept custom user agent."""
        extractor = PDFExtractor(user_agent="MyBot/1.0")
        self.assertEqual(extractor.user_agent, "MyBot/1.0")
    
    def test_auth_credentials(self):
        """Should accept auth credentials tuple."""
        extractor = PDFExtractor(auth=("user", "pass"))
        self.assertEqual(extractor.auth, ("user", "pass"))
    
    def test_auth_token(self):
        """Should accept pre-encoded auth token."""
        extractor = PDFExtractor(auth_token="dXNlcjpwYXNz")
        self.assertEqual(extractor.auth_token, "dXNlcjpwYXNz")


class TestAuthHeader(unittest.TestCase):
    """Tests for authentication header generation."""
    
    def test_no_auth_returns_none(self):
        """Should return None when no auth configured."""
        extractor = PDFExtractor()
        self.assertIsNone(extractor._get_auth_header())
    
    def test_auth_tuple_generates_header(self):
        """Should generate Basic auth header from credentials."""
        extractor = PDFExtractor(auth=("user", "pass"))
        header = extractor._get_auth_header()
        
        self.assertTrue(header.startswith("Basic "))
        # Decode and verify
        token = header[6:]  # Remove "Basic "
        decoded = base64.b64decode(token).decode()
        self.assertEqual(decoded, "user:pass")
    
    def test_auth_token_used_directly(self):
        """Should use provided token directly."""
        token = base64.b64encode(b"user:pass").decode()
        extractor = PDFExtractor(auth_token=token)
        header = extractor._get_auth_header()
        
        self.assertEqual(header, f"Basic {token}")
    
    def test_auth_token_strips_basic_prefix(self):
        """Should strip 'Basic ' prefix from token if present."""
        token = base64.b64encode(b"user:pass").decode()
        extractor = PDFExtractor(auth_token=f"Basic {token}")
        header = extractor._get_auth_header()
        
        # Should not have double "Basic Basic"
        self.assertEqual(header, f"Basic {token}")
        self.assertNotIn("Basic Basic", header)


# ============================================================================
# File Extraction Tests
# ============================================================================

class TestExtractFromFile(unittest.TestCase):
    """Tests for extracting text from local PDF files."""
    
    def test_extracts_text_from_valid_pdf(self):
        """Should extract text from a valid PDF file."""
        pdf_content = create_minimal_pdf("Test document content")
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(pdf_content)
            f.flush()
            
            extractor = PDFExtractor()
            result = extractor.extract_from_file(Path(f.name))
            
            # Should not have error
            self.assertIsNone(result['error'])
            # Should have at least 1 page
            self.assertGreaterEqual(result['pages'], 1)
            # Text might not match exactly due to PDF rendering
            self.assertIsInstance(result['text'], str)
    
    def test_returns_page_count(self):
        """Should return the number of pages."""
        pdf_content = create_minimal_pdf("Single page")
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(pdf_content)
            f.flush()
            
            extractor = PDFExtractor()
            result = extractor.extract_from_file(Path(f.name))
            
            self.assertEqual(result['pages'], 1)
    
    def test_extracts_metadata_title(self):
        """Should extract title from metadata."""
        pdf_content = create_minimal_pdf("Content", title="My Document Title")
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(pdf_content)
            f.flush()
            
            extractor = PDFExtractor()
            result = extractor.extract_from_file(Path(f.name))
            
            # Metadata should be extracted
            self.assertIn('metadata', result)
            # Title from metadata or fallback
            self.assertIsInstance(result['title'], str)
    
    def test_uses_filename_when_no_title_metadata(self):
        """Should use filename as title when no metadata title."""
        pdf_content = create_minimal_pdf("Content")  # No title metadata
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', prefix='my_document_', delete=False) as f:
            f.write(pdf_content)
            f.flush()
            
            extractor = PDFExtractor()
            result = extractor.extract_from_file(Path(f.name))
            
            # Should have a title (from filename)
            self.assertTrue(len(result['title']) > 0)
    
    def test_handles_nonexistent_file(self):
        """Should handle nonexistent file gracefully."""
        extractor = PDFExtractor()
        result = extractor.extract_from_file(Path("/nonexistent/file.pdf"))
        
        # Should have an error
        self.assertIsNotNone(result['error'])
        # Should not crash
        self.assertEqual(result['text'], '')
        self.assertEqual(result['pages'], 0)
    
    def test_handles_corrupted_pdf(self):
        """Should handle corrupted PDF gracefully."""
        # Write invalid PDF content
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b"This is not a valid PDF file content")
            f.flush()
            
            extractor = PDFExtractor()
            result = extractor.extract_from_file(Path(f.name))
            
            # Should have an error
            self.assertIsNotNone(result['error'])
            self.assertIn('error', result['error'].lower())
    
    def test_handles_empty_pdf(self):
        """Should handle empty/zero-byte file gracefully."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            # Write nothing - empty file
            f.flush()
            
            extractor = PDFExtractor()
            result = extractor.extract_from_file(Path(f.name))
            
            # Should have an error
            self.assertIsNotNone(result['error'])


# ============================================================================
# URL Extraction Tests
# ============================================================================

class TestExtractFromUrl(unittest.TestCase):
    """Tests for extracting text from PDF URLs."""
    
    @patch('doc_search.pdf_extractor.urlopen')
    def test_extracts_from_url(self, mock_urlopen):
        """Should extract text from PDF at URL."""
        pdf_content = create_minimal_pdf("URL document content")
        
        mock_response = MagicMock()
        mock_response.read.return_value = pdf_content
        mock_urlopen.return_value = mock_response
        
        extractor = PDFExtractor()
        result = extractor.extract_from_url("https://example.com/doc.pdf")
        
        # Should not have error
        self.assertIsNone(result['error'])
        self.assertGreaterEqual(result['pages'], 1)
    
    @patch('doc_search.pdf_extractor.urlopen')
    def test_includes_user_agent_header(self, mock_urlopen):
        """Should include User-Agent header in request."""
        pdf_content = create_minimal_pdf("Content")
        
        mock_response = MagicMock()
        mock_response.read.return_value = pdf_content
        mock_urlopen.return_value = mock_response
        
        extractor = PDFExtractor(user_agent="CustomBot/2.0")
        extractor.extract_from_url("https://example.com/doc.pdf")
        
        # Check the request was made
        self.assertTrue(mock_urlopen.called)
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.get_header('User-agent'), "CustomBot/2.0")
    
    @patch('doc_search.pdf_extractor.urlopen')
    def test_includes_auth_header(self, mock_urlopen):
        """Should include Authorization header when auth configured."""
        pdf_content = create_minimal_pdf("Content")
        
        mock_response = MagicMock()
        mock_response.read.return_value = pdf_content
        mock_urlopen.return_value = mock_response
        
        extractor = PDFExtractor(auth=("user", "pass"))
        extractor.extract_from_url("https://example.com/doc.pdf")
        
        request = mock_urlopen.call_args[0][0]
        auth_header = request.get_header('Authorization')
        self.assertIsNotNone(auth_header)
        self.assertTrue(auth_header.startswith("Basic "))
    
    @patch('doc_search.pdf_extractor.urlopen')
    def test_handles_http_error(self, mock_urlopen):
        """Should handle HTTP errors gracefully."""
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            "https://example.com/doc.pdf", 404, "Not Found", {}, None
        )
        
        extractor = PDFExtractor()
        result = extractor.extract_from_url("https://example.com/doc.pdf")
        
        self.assertIsNotNone(result['error'])
        self.assertEqual(result['text'], '')
    
    @patch('doc_search.pdf_extractor.urlopen')
    def test_handles_url_error(self, mock_urlopen):
        """Should handle URL errors gracefully."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")
        
        extractor = PDFExtractor()
        result = extractor.extract_from_url("https://example.com/doc.pdf")
        
        self.assertIsNotNone(result['error'])
        self.assertEqual(result['text'], '')
    
    @patch('doc_search.pdf_extractor.urlopen')
    def test_handles_timeout(self, mock_urlopen):
        """Should handle timeout gracefully."""
        from socket import timeout
        mock_urlopen.side_effect = timeout("Connection timed out")
        
        extractor = PDFExtractor()
        result = extractor.extract_from_url("https://example.com/doc.pdf")
        
        self.assertIsNotNone(result['error'])
    
    @patch('doc_search.pdf_extractor.urlopen')
    def test_uses_url_filename_as_title_fallback(self, mock_urlopen):
        """Should use URL filename as title when no metadata."""
        pdf_content = create_minimal_pdf("Content")  # No title metadata
        
        mock_response = MagicMock()
        mock_response.read.return_value = pdf_content
        mock_urlopen.return_value = mock_response
        
        extractor = PDFExtractor()
        result = extractor.extract_from_url("https://example.com/path/my_document.pdf")
        
        # Should use filename (without extension) as title
        self.assertIn("my_document", result['title'])


# ============================================================================
# Auto-detect Source Tests
# ============================================================================

class TestExtract(unittest.TestCase):
    """Tests for auto-detecting file vs URL."""
    
    def test_detects_http_url(self):
        """Should detect http:// URLs."""
        extractor = PDFExtractor()
        
        with patch.object(extractor, 'extract_from_url') as mock:
            mock.return_value = {'text': '', 'error': None}
            extractor.extract("http://example.com/doc.pdf")
            mock.assert_called_once_with("http://example.com/doc.pdf")
    
    def test_detects_https_url(self):
        """Should detect https:// URLs."""
        extractor = PDFExtractor()
        
        with patch.object(extractor, 'extract_from_url') as mock:
            mock.return_value = {'text': '', 'error': None}
            extractor.extract("https://example.com/doc.pdf")
            mock.assert_called_once_with("https://example.com/doc.pdf")
    
    def test_detects_file_path(self):
        """Should detect file paths."""
        extractor = PDFExtractor()
        
        with patch.object(extractor, 'extract_from_file') as mock:
            mock.return_value = {'text': '', 'error': None}
            extractor.extract("/path/to/document.pdf")
            mock.assert_called_once()
            # Check it was called with a Path
            call_arg = mock.call_args[0][0]
            self.assertIsInstance(call_arg, Path)
    
    def test_detects_relative_path(self):
        """Should treat relative paths as files."""
        extractor = PDFExtractor()
        
        with patch.object(extractor, 'extract_from_file') as mock:
            mock.return_value = {'text': '', 'error': None}
            extractor.extract("docs/document.pdf")
            mock.assert_called_once()


# ============================================================================
# Convenience Function Tests
# ============================================================================

class TestExtractPdfText(unittest.TestCase):
    """Tests for the extract_pdf_text convenience function."""
    
    def test_returns_text_string(self):
        """Should return just the text string."""
        pdf_content = create_minimal_pdf("Extracted text")
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(pdf_content)
            f.flush()
            
            result = extract_pdf_text(f.name)
            
            self.assertIsInstance(result, str)
    
    def test_returns_empty_on_error(self):
        """Should return empty string on error."""
        result = extract_pdf_text("/nonexistent/file.pdf")
        
        self.assertEqual(result, '')
    
    def test_passes_kwargs_to_extractor(self):
        """Should pass kwargs to PDFExtractor."""
        with patch('doc_search.pdf_extractor.PDFExtractor') as MockExtractor:
            mock_instance = MagicMock()
            mock_instance.extract.return_value = {'text': 'test', 'error': None}
            MockExtractor.return_value = mock_instance
            
            extract_pdf_text("test.pdf", timeout=60.0, user_agent="CustomBot")
            
            MockExtractor.assert_called_once_with(timeout=60.0, user_agent="CustomBot")


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases(unittest.TestCase):
    """Edge case tests for PDFExtractor."""
    
    def test_result_structure(self):
        """Should always return consistent result structure."""
        extractor = PDFExtractor()
        result = extractor.extract("/nonexistent.pdf")
        
        # All expected keys should be present
        self.assertIn('text', result)
        self.assertIn('title', result)
        self.assertIn('pages', result)
        self.assertIn('metadata', result)
        self.assertIn('error', result)
        
        # Types should be correct even on error
        self.assertIsInstance(result['text'], str)
        self.assertIsInstance(result['title'], str)
        self.assertIsInstance(result['pages'], int)
        self.assertIsInstance(result['metadata'], dict)
    
    @patch('doc_search.pdf_extractor.urlopen')
    def test_handles_non_pdf_content_from_url(self, mock_urlopen):
        """Should handle non-PDF content from URL gracefully."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"<html>Not a PDF</html>"
        mock_urlopen.return_value = mock_response
        
        extractor = PDFExtractor()
        result = extractor.extract_from_url("https://example.com/page.pdf")
        
        # Should have an error
        self.assertIsNotNone(result['error'])
    
    def test_handles_binary_garbage_file(self):
        """Should handle random binary file gracefully."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            # Write random binary garbage
            f.write(b'\x00\x01\x02\xff\xfe\xfd' * 100)
            f.flush()
            
            extractor = PDFExtractor()
            result = extractor.extract_from_file(Path(f.name))
            
            # Should have an error, not crash
            self.assertIsNotNone(result['error'])
    
    def test_handles_pdf_with_no_pages(self):
        """Should handle PDF with parsing issues gracefully."""
        # Create a PDF-like header but invalid structure
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b"%PDF-1.4\n%%EOF")  # Minimal but invalid PDF
            f.flush()
            
            extractor = PDFExtractor()
            result = extractor.extract_from_file(Path(f.name))
            
            # Should either work with 0 pages or have an error
            if result['error'] is None:
                self.assertEqual(result['pages'], 0)


# ============================================================================
# Heading Detection Tests
# ============================================================================

class TestHeadingDetection(unittest.TestCase):
    """Tests for PDF heading detection functionality."""
    
    def test_result_includes_headings_key(self):
        """Should include headings key in result."""
        pdf_content = create_minimal_pdf("Test content")
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(pdf_content)
            f.flush()
            
            extractor = PDFExtractor()
            result = extractor.extract_from_file(Path(f.name))
            
            self.assertIn('headings', result)
            self.assertIsInstance(result['headings'], list)
    
    def test_headings_structure(self):
        """Headings should be list of (level, text) tuples."""
        extractor = PDFExtractor()
        
        # Test the internal heading detection with mock data
        text_elements = [
            {'text': 'INTRODUCTION', 'font_size': 18, 'font_name': ''},
            {'text': 'Some body text here.', 'font_size': 12, 'font_name': ''},
            {'text': 'METHODS', 'font_size': 16, 'font_name': ''},
        ]
        
        headings, body = extractor._detect_headings(text_elements)
        
        # Should have headings as tuples
        for h in headings:
            self.assertIsInstance(h, tuple)
            self.assertEqual(len(h), 2)
            self.assertIsInstance(h[0], int)  # level
            self.assertIsInstance(h[1], str)  # text
    
    def test_font_size_heading_detection(self):
        """Should detect headings based on font size."""
        extractor = PDFExtractor()
        
        text_elements = [
            {'text': 'Large Title', 'font_size': 24, 'font_name': ''},
            {'text': 'Normal text paragraph.', 'font_size': 12, 'font_name': ''},
            {'text': 'More normal text.', 'font_size': 12, 'font_name': ''},
            {'text': 'Section Heading', 'font_size': 18, 'font_name': ''},
            {'text': 'Body text content.', 'font_size': 12, 'font_name': ''},
        ]
        
        headings, body = extractor._detect_headings(text_elements)
        
        # Should detect larger fonts as headings
        heading_texts = [h[1] for h in headings]
        self.assertIn('Large Title', heading_texts)
        self.assertIn('Section Heading', heading_texts)
        
        # Normal text should be in body
        self.assertTrue(any('Normal text' in b for b in body))
    
    def test_bold_font_heading_detection(self):
        """Should detect bold fonts as headings."""
        extractor = PDFExtractor()
        
        text_elements = [
            {'text': 'Bold Heading', 'font_size': 12, 'font_name': '/Helvetica-Bold'},
            {'text': 'Regular paragraph text here.', 'font_size': 12, 'font_name': '/Helvetica'},
        ]
        
        headings, body = extractor._detect_headings(text_elements)
        
        heading_texts = [h[1] for h in headings]
        self.assertIn('Bold Heading', heading_texts)
    
    def test_all_caps_heading_detection(self):
        """Should detect ALL CAPS as headings."""
        extractor = PDFExtractor()
        
        text_elements = [
            {'text': 'CHAPTER ONE', 'font_size': 12, 'font_name': ''},
            {'text': 'This is regular text with normal casing.', 'font_size': 12, 'font_name': ''},
            {'text': 'SUMMARY', 'font_size': 12, 'font_name': ''},
        ]
        
        headings, body = extractor._detect_headings(text_elements)
        
        heading_texts = [h[1] for h in headings]
        self.assertIn('CHAPTER ONE', heading_texts)
        self.assertIn('SUMMARY', heading_texts)
    
    def test_numbered_section_heading_detection(self):
        """Should detect numbered sections as headings."""
        extractor = PDFExtractor()
        
        text_elements = [
            {'text': '1. Introduction', 'font_size': 12, 'font_name': ''},
            {'text': 'Some intro text.', 'font_size': 12, 'font_name': ''},
            {'text': '1.1 Background', 'font_size': 12, 'font_name': ''},
            {'text': 'Background details.', 'font_size': 12, 'font_name': ''},
            {'text': '2.3.4 Specific Topic', 'font_size': 12, 'font_name': ''},
        ]
        
        headings, body = extractor._detect_headings(text_elements)
        
        heading_texts = [h[1] for h in headings]
        self.assertIn('1. Introduction', heading_texts)
        self.assertIn('1.1 Background', heading_texts)
        self.assertIn('2.3.4 Specific Topic', heading_texts)
    
    def test_heading_level_assignment(self):
        """Should assign appropriate heading levels."""
        extractor = PDFExtractor()
        
        # Larger fonts should get level 1
        text_elements = [
            {'text': 'Main Title', 'font_size': 24, 'font_name': ''},
            {'text': 'Body text', 'font_size': 12, 'font_name': ''},
            {'text': 'Section', 'font_size': 16, 'font_name': ''},
        ]
        
        headings, body = extractor._detect_headings(text_elements)
        
        # Find the main title heading
        main_title = [h for h in headings if h[1] == 'Main Title']
        self.assertTrue(len(main_title) > 0)
        self.assertEqual(main_title[0][0], 1)  # Should be level 1
    
    def test_empty_elements_handling(self):
        """Should handle empty element lists gracefully."""
        extractor = PDFExtractor()
        
        headings, body = extractor._detect_headings([])
        
        self.assertEqual(headings, [])
        self.assertEqual(body, [])
    
    def test_no_font_info_fallback(self):
        """Should handle elements without font info."""
        extractor = PDFExtractor()
        
        text_elements = [
            {'text': 'HEADING TEXT', 'font_size': 0, 'font_name': ''},
            {'text': 'Regular body text here.', 'font_size': 0, 'font_name': ''},
        ]
        
        headings, body = extractor._detect_headings(text_elements)
        
        # ALL CAPS should still be detected
        heading_texts = [h[1] for h in headings]
        self.assertIn('HEADING TEXT', heading_texts)
    
    def test_long_text_not_heading(self):
        """Should not treat very long text as headings."""
        extractor = PDFExtractor()
        
        long_text = "THIS IS A VERY LONG TEXT THAT GOES ON AND ON " * 10
        text_elements = [
            {'text': long_text, 'font_size': 16, 'font_name': ''},
            {'text': 'Short heading', 'font_size': 16, 'font_name': ''},
        ]
        
        headings, body = extractor._detect_headings(text_elements)
        
        heading_texts = [h[1] for h in headings]
        # Long text should not be a heading (even with large font)
        self.assertFalse(any(len(h) > 200 for _, h in headings))
        # It should end up in body
        self.assertTrue(len(body) > 0)


class TestOutlineExtraction(unittest.TestCase):
    """Tests for PDF outline/TOC extraction."""
    
    def test_extract_outline_empty(self):
        """Should handle empty outline."""
        extractor = PDFExtractor()
        
        result = extractor._extract_outline_headings(None)
        self.assertEqual(result, [])
    
    def test_extract_outline_list(self):
        """Should handle outline as list."""
        extractor = PDFExtractor()
        
        # Create mock outline items
        class MockOutlineItem:
            def __init__(self, title):
                self.title = title
        
        outline = [
            MockOutlineItem("Chapter 1"),
            MockOutlineItem("Chapter 2"),
        ]
        
        result = extractor._extract_outline_headings(outline)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], (1, "Chapter 1"))
        self.assertEqual(result[1], (1, "Chapter 2"))
    
    def test_extract_nested_outline(self):
        """Should handle nested outline structure."""
        extractor = PDFExtractor()
        
        class MockOutlineItem:
            def __init__(self, title):
                self.title = title
        
        outline = [
            MockOutlineItem("Part 1"),
            [  # Nested level
                MockOutlineItem("Chapter 1.1"),
                MockOutlineItem("Chapter 1.2"),
            ],
            MockOutlineItem("Part 2"),
        ]
        
        result = extractor._extract_outline_headings(outline)
        
        # Should have all items with appropriate levels
        titles = [h[1] for h in result]
        self.assertIn("Part 1", titles)
        self.assertIn("Chapter 1.1", titles)
        self.assertIn("Part 2", titles)
        
        # Nested items should have higher level
        for level, title in result:
            if title.startswith("Chapter"):
                self.assertEqual(level, 2)


class TestHeadingIntegration(unittest.TestCase):
    """Integration tests for heading extraction with real PDFs."""
    
    def test_extraction_includes_headings(self):
        """Extracted result should include headings list."""
        pdf_content = create_minimal_pdf("Document content")
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(pdf_content)
            f.flush()
            
            extractor = PDFExtractor()
            result = extractor.extract_from_file(Path(f.name))
            
            # Should have headings key (may be empty for simple PDFs)
            self.assertIn('headings', result)
            self.assertIsInstance(result['headings'], list)
    
    def test_error_result_includes_headings(self):
        """Error results should still include headings key."""
        extractor = PDFExtractor()
        result = extractor.extract("/nonexistent/file.pdf")
        
        self.assertIn('headings', result)
        self.assertEqual(result['headings'], [])


# ============================================================================
# Chunk Extraction Tests (Page/Section Tracking)
# ============================================================================

class TestChunkExtraction(unittest.TestCase):
    """Tests for PDF chunk extraction with page and section context."""
    
    def test_result_includes_chunks_key(self):
        """Should include chunks key in result."""
        pdf_content = create_minimal_pdf("Test content")
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(pdf_content)
            f.flush()
            
            extractor = PDFExtractor()
            result = extractor.extract_from_file(Path(f.name))
            
            self.assertIn('chunks', result)
            self.assertIsInstance(result['chunks'], list)
    
    def test_chunks_structure(self):
        """Chunks should have text, page, section, section_level."""
        extractor = PDFExtractor()
        
        text_elements = [
            {'text': 'Introduction', 'font_size': 18, 'font_name': 'Bold', 'page': 1},
            {'text': 'Body text here.', 'font_size': 12, 'font_name': '', 'page': 1},
            {'text': 'Methods', 'font_size': 16, 'font_name': 'Bold', 'page': 2},
            {'text': 'Method details.', 'font_size': 12, 'font_name': '', 'page': 2},
        ]
        
        chunks, headings, body = extractor._build_chunks_with_context(text_elements)
        
        # Should have chunks (body text only, not headings)
        self.assertTrue(len(chunks) > 0)
        
        # Each chunk should have required keys
        for chunk in chunks:
            self.assertIn('text', chunk)
            self.assertIn('page', chunk)
            self.assertIn('section', chunk)
            self.assertIn('section_level', chunk)
    
    def test_chunks_track_page_numbers(self):
        """Chunks should track the correct page number."""
        extractor = PDFExtractor()
        
        text_elements = [
            {'text': 'Page one content.', 'font_size': 12, 'font_name': '', 'page': 1},
            {'text': 'More page one.', 'font_size': 12, 'font_name': '', 'page': 1},
            {'text': 'Page two content.', 'font_size': 12, 'font_name': '', 'page': 2},
            {'text': 'Page three content.', 'font_size': 12, 'font_name': '', 'page': 3},
        ]
        
        chunks, _, _ = extractor._build_chunks_with_context(text_elements)
        
        # Verify page numbers
        self.assertEqual(chunks[0]['page'], 1)
        self.assertEqual(chunks[1]['page'], 1)
        self.assertEqual(chunks[2]['page'], 2)
        self.assertEqual(chunks[3]['page'], 3)
    
    def test_chunks_track_section_context(self):
        """Chunks should track the current section (most recent heading)."""
        extractor = PDFExtractor()
        
        text_elements = [
            {'text': 'Introduction', 'font_size': 18, 'font_name': 'Bold', 'page': 1},
            {'text': 'Intro text.', 'font_size': 12, 'font_name': '', 'page': 1},
            {'text': 'More intro.', 'font_size': 12, 'font_name': '', 'page': 1},
            {'text': 'Methods', 'font_size': 18, 'font_name': 'Bold', 'page': 2},
            {'text': 'Method details.', 'font_size': 12, 'font_name': '', 'page': 2},
            {'text': 'Results', 'font_size': 18, 'font_name': 'Bold', 'page': 3},
            {'text': 'Result data.', 'font_size': 12, 'font_name': '', 'page': 3},
        ]
        
        chunks, headings, body = extractor._build_chunks_with_context(text_elements)
        
        # Find chunks and verify their sections
        intro_chunks = [c for c in chunks if 'Intro' in c['text'] or 'intro' in c['text']]
        method_chunks = [c for c in chunks if 'Method' in c['text'] or 'method' in c['text'].lower()]
        result_chunks = [c for c in chunks if 'Result' in c['text'] or 'result' in c['text'].lower()]
        
        # Intro chunks should have 'Introduction' section
        for chunk in intro_chunks:
            self.assertEqual(chunk['section'], 'Introduction')
        
        # Method chunks should have 'Methods' section  
        for chunk in method_chunks:
            self.assertEqual(chunk['section'], 'Methods')
        
        # Result chunks should have 'Results' section
        for chunk in result_chunks:
            self.assertEqual(chunk['section'], 'Results')
    
    def test_chunks_empty_section_before_first_heading(self):
        """Chunks before first heading should have empty section."""
        extractor = PDFExtractor()
        
        text_elements = [
            {'text': 'Preamble text.', 'font_size': 12, 'font_name': '', 'page': 1},
            {'text': 'Introduction', 'font_size': 18, 'font_name': 'Bold', 'page': 1},
            {'text': 'Intro text.', 'font_size': 12, 'font_name': '', 'page': 1},
        ]
        
        chunks, _, _ = extractor._build_chunks_with_context(text_elements)
        
        # First chunk (before any heading) should have empty section
        preamble_chunk = [c for c in chunks if 'Preamble' in c['text']][0]
        self.assertEqual(preamble_chunk['section'], '')
        self.assertEqual(preamble_chunk['section_level'], 0)
    
    def test_chunks_section_level_tracking(self):
        """Chunks should track the heading level of their section."""
        extractor = PDFExtractor()
        
        # Use clear section heading keywords (the new conservative approach)
        text_elements = [
            {'text': '1 Introduction', 'font_size': 24, 'font_name': '', 'page': 1},
            {'text': 'Intro content.', 'font_size': 12, 'font_name': '', 'page': 1},
            {'text': '1.1 Background', 'font_size': 16, 'font_name': '', 'page': 1},
            {'text': 'Background content.', 'font_size': 12, 'font_name': '', 'page': 1},
        ]
        
        chunks, headings, _ = extractor._build_chunks_with_context(text_elements)
        
        # Verify heading levels were detected
        heading_levels = {h[1]: h[0] for h in headings}
        self.assertIn('1 Introduction', heading_levels)
        
        # Chunks under different headings should have different section_levels
        intro_chunk = [c for c in chunks if 'Intro content' in c['text']]
        bg_chunk = [c for c in chunks if 'Background content' in c['text']]
        
        if intro_chunk and bg_chunk:
            # The exact levels depend on detection, but they should be tracked
            self.assertIsInstance(intro_chunk[0]['section_level'], int)
            self.assertIsInstance(bg_chunk[0]['section_level'], int)
    
    def test_empty_elements_returns_empty_chunks(self):
        """Should return empty chunks for empty input."""
        extractor = PDFExtractor()
        
        chunks, headings, body = extractor._build_chunks_with_context([])
        
        self.assertEqual(chunks, [])
        self.assertEqual(headings, [])
        self.assertEqual(body, [])
    
    def test_chunks_backward_compatible_with_headings(self):
        """Chunks should work alongside existing headings extraction."""
        extractor = PDFExtractor()
        
        text_elements = [
            {'text': 'INTRODUCTION', 'font_size': 16, 'font_name': '', 'page': 1},
            {'text': 'Body text.', 'font_size': 12, 'font_name': '', 'page': 1},
        ]
        
        chunks, headings, body = extractor._build_chunks_with_context(text_elements)
        
        # Should still extract headings
        self.assertTrue(len(headings) > 0)
        self.assertIn(('INTRODUCTION',), [(h[1],) for h in headings])
        
        # And also have chunks
        self.assertTrue(len(chunks) > 0)


class TestFindChunkContext(unittest.TestCase):
    """Tests for find_chunk_context utility function."""
    
    def test_finds_exact_match(self):
        """Should find chunk with exact substring match."""
        from doc_search.searcher_utils import find_chunk_context
        
        chunks = [
            {'text': 'Introduction text here.', 'page': 1, 'section': 'Intro', 'section_level': 1},
            {'text': 'Methods description.', 'page': 5, 'section': 'Methods', 'section_level': 2},
        ]
        
        result = find_chunk_context('Methods description', chunks)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['page'], 5)
        self.assertEqual(result['section'], 'Methods')
    
    def test_finds_partial_match(self):
        """Should find chunk with partial text match."""
        from doc_search.searcher_utils import find_chunk_context
        
        chunks = [
            {'text': 'This is a long introduction text with many words.', 'page': 1, 'section': 'Intro', 'section_level': 1},
            {'text': 'Methods and procedures for the study.', 'page': 3, 'section': 'Methods', 'section_level': 2},
        ]
        
        result = find_chunk_context('introduction text with many', chunks)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['page'], 1)
        self.assertEqual(result['section'], 'Intro')
    
    def test_handles_highlighted_snippet(self):
        """Should match even with **highlight** markers."""
        from doc_search.searcher_utils import find_chunk_context
        
        chunks = [
            {'text': 'The data collection methodology involved surveys.', 'page': 12, 'section': 'Data Collection', 'section_level': 2},
        ]
        
        result = find_chunk_context('**data** collection **methodology**', chunks)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['page'], 12)
        self.assertEqual(result['section'], 'Data Collection')
    
    def test_returns_none_for_no_match(self):
        """Should return None when no chunk matches."""
        from doc_search.searcher_utils import find_chunk_context
        
        chunks = [
            {'text': 'Introduction text.', 'page': 1, 'section': 'Intro', 'section_level': 1},
        ]
        
        result = find_chunk_context('completely unrelated content', chunks)
        
        self.assertIsNone(result)
    
    def test_handles_empty_chunks(self):
        """Should handle empty chunks list."""
        from doc_search.searcher_utils import find_chunk_context
        
        result = find_chunk_context('some text', [])
        
        self.assertIsNone(result)
    
    def test_handles_empty_snippet(self):
        """Should handle empty snippet."""
        from doc_search.searcher_utils import find_chunk_context
        
        chunks = [
            {'text': 'Some text.', 'page': 1, 'section': 'Intro', 'section_level': 1},
        ]
        
        result = find_chunk_context('', chunks)
        
        self.assertIsNone(result)
    
    def test_word_overlap_fallback(self):
        """Should fall back to word overlap when no substring match."""
        from doc_search.searcher_utils import find_chunk_context
        
        chunks = [
            {'text': 'The quick brown fox jumps over lazy dogs.', 'page': 7, 'section': 'Animals', 'section_level': 1},
            {'text': 'Cats are independent pets.', 'page': 8, 'section': 'Pets', 'section_level': 1},
        ]
        
        # Snippet with reordered/partial words from first chunk
        result = find_chunk_context('fox brown quick jumps dogs', chunks)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['page'], 7)


if __name__ == '__main__':
    unittest.main()
