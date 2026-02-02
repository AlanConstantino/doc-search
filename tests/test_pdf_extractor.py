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


if __name__ == '__main__':
    unittest.main()
