"""
Tests for the Word document extractor module.

Tests Word (.docx) extraction using pure Python stdlib
(zipfile + xml.etree.ElementTree).
"""

import unittest
import tempfile
import zipfile
from pathlib import Path

from doc_search.word_extractor import WordExtractor, extract_word_text


class TestWordExtractor(unittest.TestCase):
    """Tests for Word (.docx) extraction."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.fixtures_dir = Path(__file__).parent / 'fixtures' / 'word'
        cls.sample_docx = cls.fixtures_dir / 'sample.docx'
        cls.no_metadata_docx = cls.fixtures_dir / 'no_metadata.docx'
        cls.with_header_footer_docx = cls.fixtures_dir / 'with_header_footer.docx'
        cls.with_tabs_breaks_docx = cls.fixtures_dir / 'with_tabs_breaks.docx'
        
        # Ensure fixtures exist
        if not cls.sample_docx.exists():
            import sys
            sys.path.insert(0, str(cls.fixtures_dir))
            from create_fixtures import (
                create_sample_docx, create_no_metadata_docx,
                create_with_header_footer_docx, create_with_tabs_breaks_docx
            )
            create_sample_docx()
            create_no_metadata_docx()
            create_with_header_footer_docx()
            create_with_tabs_breaks_docx()
    
    def test_extract_document(self):
        """Extract text from a Word document."""
        extractor = WordExtractor()
        result = extractor.extract_from_file(self.sample_docx)
        
        self.assertIsNone(result['error'])
        self.assertEqual(result['title'], 'Test Document')
        self.assertIn('file://', result['url'])
        
        # Check text content
        text = result['text']
        self.assertIn('Introduction', text)
        self.assertIn('first paragraph', text)
        self.assertIn('Methods', text)
        self.assertIn('Results', text)
    
    def test_extract_headings(self):
        """Heading styles should be detected."""
        extractor = WordExtractor()
        result = extractor.extract_from_file(self.sample_docx)
        
        headings = result['headings']
        
        # Should have H1 and H2 headings
        h1_headings = [h for h in headings if h[0] == 1]
        h2_headings = [h for h in headings if h[0] == 2]
        
        self.assertEqual(len(h1_headings), 1)
        self.assertEqual(len(h2_headings), 2)
        
        heading_texts = [h[1] for h in headings]
        self.assertIn('Introduction', heading_texts)
        self.assertIn('Methods', heading_texts)
        self.assertIn('Results', heading_texts)
    
    def test_extract_metadata(self):
        """Document properties should be extracted."""
        extractor = WordExtractor()
        result = extractor.extract_from_file(self.sample_docx)
        
        meta = result['metadata']
        self.assertEqual(meta['doc_type'], 'docx')
        self.assertEqual(meta['title'], 'Test Document')
        self.assertEqual(meta['author'], 'Test Author')
        self.assertIn('word_count', meta)
        self.assertIn('created', meta)
        self.assertIn('modified', meta)
    
    def test_extract_no_metadata(self):
        """Document without metadata should use filename as title."""
        extractor = WordExtractor()
        result = extractor.extract_from_file(self.no_metadata_docx)
        
        self.assertIsNone(result['error'])
        # Should fall back to filename
        self.assertEqual(result['title'], 'no_metadata')
        self.assertIn('no title or author', result['text'])
    
    def test_extract_header_footer(self):
        """Headers and footers should be extracted."""
        extractor = WordExtractor()
        result = extractor.extract_from_file(self.with_header_footer_docx)
        
        self.assertIsNone(result['error'])
        text = result['text']
        
        self.assertIn('CONFIDENTIAL HEADER', text)
        self.assertIn('Page Footer', text)
        self.assertIn('Main document content', text)
    
    def test_extract_tabs_and_breaks(self):
        """Tabs and line breaks should be preserved."""
        extractor = WordExtractor()
        result = extractor.extract_from_file(self.with_tabs_breaks_docx)
        
        self.assertIsNone(result['error'])
        text = result['text']
        
        # Check tabs are converted
        self.assertIn('\t', text)
        self.assertIn('Column1', text)
        self.assertIn('Column2', text)
        
        # Check line breaks
        self.assertIn('Line one', text)
        self.assertIn('Line two after break', text)
    
    def test_extract_invalid_file(self):
        """Extraction should handle invalid files gracefully."""
        extractor = WordExtractor()
        
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            f.write(b'not a valid docx file')
            temp_path = Path(f.name)
        
        try:
            result = extractor.extract_from_file(temp_path)
            self.assertIsNotNone(result['error'])
            self.assertIn('Invalid', result['error'])
        finally:
            temp_path.unlink()
    
    def test_file_not_found(self):
        """Should handle non-existent file gracefully."""
        extractor = WordExtractor()
        result = extractor.extract_from_file(Path('/nonexistent/file.docx'))
        
        self.assertIsNotNone(result['error'])
        self.assertIn('not found', result['error'].lower())
    
    def test_extract_returns_list(self):
        """extract() should return a list for consistency with ExcelExtractor."""
        extractor = WordExtractor()
        results = extractor.extract(self.sample_docx)
        
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Test Document')
    
    def test_word_count(self):
        """Word count should be calculated correctly."""
        extractor = WordExtractor()
        result = extractor.extract_from_file(self.sample_docx)
        
        word_count = result['metadata'].get('word_count', 0)
        self.assertGreater(word_count, 0)
        # Sample doc has several sentences
        self.assertGreater(word_count, 20)


class TestExtractWordText(unittest.TestCase):
    """Tests for the convenience function."""
    
    @classmethod
    def setUpClass(cls):
        cls.fixtures_dir = Path(__file__).parent / 'fixtures' / 'word'
        cls.sample_docx = cls.fixtures_dir / 'sample.docx'
    
    def test_extract_word_text(self):
        """Convenience function should return text."""
        text = extract_word_text(str(self.sample_docx))
        
        self.assertIn('Introduction', text)
        self.assertIn('Methods', text)
    
    def test_extract_word_text_invalid_file(self):
        """Should return empty string for invalid file."""
        text = extract_word_text('/nonexistent/file.docx')
        self.assertEqual(text, '')


class TestWordHeadingDetection(unittest.TestCase):
    """Tests for heading style detection."""
    
    def test_heading_patterns(self):
        """Test heading style name pattern matching."""
        extractor = WordExtractor()
        
        # Standard headings
        self.assertEqual(extractor._get_heading_level('Heading 1'), 1)
        self.assertEqual(extractor._get_heading_level('Heading 2'), 2)
        self.assertEqual(extractor._get_heading_level('Heading 3'), 3)
        self.assertEqual(extractor._get_heading_level('Heading1'), 1)
        
        # Title/Subtitle
        self.assertEqual(extractor._get_heading_level('Title'), 1)
        self.assertEqual(extractor._get_heading_level('Subtitle'), 2)
        
        # Non-headings
        self.assertIsNone(extractor._get_heading_level('Normal'))
        self.assertIsNone(extractor._get_heading_level('Body Text'))
        self.assertIsNone(extractor._get_heading_level(''))
        self.assertIsNone(extractor._get_heading_level(None))


class TestWordExtractorEdgeCases(unittest.TestCase):
    """Tests for edge cases in Word extraction."""
    
    def test_empty_document(self):
        """Test handling of empty document."""
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            with zipfile.ZipFile(temp_path, 'w') as zf:
                content_types = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''
                zf.writestr('[Content_Types].xml', content_types)
                
                rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
                zf.writestr('_rels/.rels', rels)
                
                document = '''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body/>
</w:document>'''
                zf.writestr('word/document.xml', document)
            
            extractor = WordExtractor()
            result = extractor.extract_from_file(temp_path)
            
            self.assertIsNone(result['error'])
            self.assertEqual(result['text'], '')
        finally:
            temp_path.unlink()
    
    def test_title_fallback_to_heading(self):
        """When no metadata title, should use first heading."""
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            with zipfile.ZipFile(temp_path, 'w') as zf:
                content_types = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>'''
                zf.writestr('[Content_Types].xml', content_types)
                
                rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
                zf.writestr('_rels/.rels', rels)
                
                doc_rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''
                zf.writestr('word/_rels/document.xml.rels', doc_rels)
                
                document = '''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
      <w:r><w:t>My Document Title</w:t></w:r>
    </w:p>
  </w:body>
</w:document>'''
                zf.writestr('word/document.xml', document)
                
                styles = '''<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="Heading 1"/>
  </w:style>
</w:styles>'''
                zf.writestr('word/styles.xml', styles)
            
            extractor = WordExtractor()
            result = extractor.extract_from_file(temp_path)
            
            # Should use the H1 heading as title
            self.assertEqual(result['title'], 'My Document Title')
        finally:
            temp_path.unlink()


if __name__ == '__main__':
    unittest.main()
