"""
Tests for the Office document extractor module.

Tests Excel (.xlsx) and Word (.docx) extraction using pure Python
standard library (zipfile + xml.etree).
"""

import unittest
import tempfile
import zipfile
from pathlib import Path

from doc_search.office_extractor import (
    ExcelExtractor, WordExtractor, OfficeExtractor
)


class TestExcelExtractor(unittest.TestCase):
    """Tests for Excel (.xlsx) extraction."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.fixtures_dir = Path(__file__).parent / 'fixtures' / 'office'
        cls.sample_xlsx = cls.fixtures_dir / 'sample.xlsx'
        cls.multi_sheet_xlsx = cls.fixtures_dir / 'multi_sheet.xlsx'
        
        # Ensure fixtures exist
        if not cls.sample_xlsx.exists():
            import sys
            sys.path.insert(0, str(cls.fixtures_dir))
            from create_fixtures import create_minimal_xlsx, create_multi_sheet_xlsx
            create_minimal_xlsx()
            create_multi_sheet_xlsx()
    
    def test_extract_single_sheet(self):
        """Extract text from a single-sheet Excel file."""
        extractor = ExcelExtractor()
        documents = extractor.extract_from_file(self.sample_xlsx)
        
        self.assertEqual(len(documents), 1)
        doc = documents[0]
        
        self.assertIsNone(doc['error'])
        self.assertIn('Q1 Summary', doc['title'])
        self.assertIn('sample.xlsx', doc['title'])
        self.assertIn('file://', doc['url'])
        self.assertIn('Q1%20Summary', doc['url'])  # URL encoded
        
        # Check metadata
        self.assertEqual(doc['metadata']['doc_type'], 'xlsx')
        self.assertEqual(doc['metadata']['sheet_name'], 'Q1 Summary')
        self.assertEqual(doc['metadata']['sheet_index'], 0)
        
        # Check text extraction with headers
        text = doc['text']
        self.assertIn('Name: John', text)
        self.assertIn('Amount: 500', text)
        self.assertIn('Name: Jane', text)
        self.assertIn('Amount: 750', text)
    
    def test_extract_multi_sheet(self):
        """Extract text from a multi-sheet Excel file."""
        extractor = ExcelExtractor()
        documents = extractor.extract_from_file(self.multi_sheet_xlsx)
        
        self.assertEqual(len(documents), 2)
        
        # First sheet
        doc1 = documents[0]
        self.assertEqual(doc1['metadata']['sheet_name'], 'Sales Data')
        self.assertIn('Product: Widget A', doc1['text'])
        self.assertIn('Revenue: 1000', doc1['text'])
        
        # Second sheet
        doc2 = documents[1]
        self.assertEqual(doc2['metadata']['sheet_name'], 'Summary')
        self.assertIn('Total', doc2['text'])
        self.assertIn('2500', doc2['text'])
    
    def test_extract_without_headers(self):
        """Extract without treating first row as headers."""
        extractor = ExcelExtractor(first_row_is_header=False)
        documents = extractor.extract_from_file(self.sample_xlsx)
        
        doc = documents[0]
        text = doc['text']
        
        # Should have raw values without header context
        self.assertIn('Name', text)  # First row values
        self.assertIn('Amount', text)
        self.assertIn('John', text)
        self.assertIn('500', text)
    
    def test_extract_invalid_file(self):
        """Extraction should handle invalid files gracefully."""
        extractor = ExcelExtractor()
        
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            f.write(b'not a valid xlsx file')
            temp_path = Path(f.name)
        
        try:
            documents = extractor.extract_from_file(temp_path)
            self.assertEqual(len(documents), 1)
            self.assertIsNotNone(documents[0]['error'])
            self.assertIn('Invalid', documents[0]['error'])
        finally:
            temp_path.unlink()
    
    def test_headings_from_header_row(self):
        """Headers should be extracted as headings."""
        extractor = ExcelExtractor()
        documents = extractor.extract_from_file(self.sample_xlsx)
        
        doc = documents[0]
        headings = doc['headings']
        
        # Header row values should appear as headings
        heading_texts = [h[1] for h in headings]
        self.assertIn('Name', heading_texts)
        self.assertIn('Amount', heading_texts)
        self.assertIn('Date', heading_texts)


class TestWordExtractor(unittest.TestCase):
    """Tests for Word (.docx) extraction."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.fixtures_dir = Path(__file__).parent / 'fixtures' / 'office'
        cls.sample_docx = cls.fixtures_dir / 'sample.docx'
        
        # Ensure fixture exists
        if not cls.sample_docx.exists():
            import sys
            sys.path.insert(0, str(cls.fixtures_dir))
            from create_fixtures import create_minimal_docx
            create_minimal_docx()
    
    def test_extract_document(self):
        """Extract text from a Word document."""
        extractor = WordExtractor()
        doc = extractor.extract_from_file(self.sample_docx)
        
        self.assertIsNone(doc['error'])
        self.assertEqual(doc['title'], 'Test Document')  # From metadata
        self.assertIn('file://', doc['url'])
        
        # Check text content
        self.assertIn('Introduction', doc['text'])
        self.assertIn('first paragraph', doc['text'])
        self.assertIn('Methods', doc['text'])
        self.assertIn('methods used', doc['text'])
    
    def test_extract_headings(self):
        """Heading styles should be detected."""
        extractor = WordExtractor()
        doc = extractor.extract_from_file(self.sample_docx)
        
        headings = doc['headings']
        
        # Should have H1 and H2 headings
        h1_headings = [h for h in headings if h[0] == 1]
        h2_headings = [h for h in headings if h[0] == 2]
        
        self.assertTrue(len(h1_headings) >= 1)
        self.assertTrue(len(h2_headings) >= 1)
        
        heading_texts = [h[1] for h in headings]
        self.assertIn('Introduction', heading_texts)
        self.assertIn('Methods', heading_texts)
    
    def test_extract_metadata(self):
        """Document properties should be extracted."""
        extractor = WordExtractor()
        doc = extractor.extract_from_file(self.sample_docx)
        
        meta = doc['metadata']
        self.assertEqual(meta['doc_type'], 'docx')
        self.assertEqual(meta['title'], 'Test Document')
        self.assertEqual(meta['author'], 'Test Author')
        self.assertIn('word_count', meta)
    
    def test_extract_invalid_file(self):
        """Extraction should handle invalid files gracefully."""
        extractor = WordExtractor()
        
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            f.write(b'not a valid docx file')
            temp_path = Path(f.name)
        
        try:
            doc = extractor.extract_from_file(temp_path)
            self.assertIsNotNone(doc['error'])
            self.assertIn('Invalid', doc['error'])
        finally:
            temp_path.unlink()


class TestOfficeExtractor(unittest.TestCase):
    """Tests for the unified OfficeExtractor."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.fixtures_dir = Path(__file__).parent / 'fixtures' / 'office'
        cls.sample_xlsx = cls.fixtures_dir / 'sample.xlsx'
        cls.sample_docx = cls.fixtures_dir / 'sample.docx'
    
    def test_is_supported(self):
        """Check supported file extensions."""
        extractor = OfficeExtractor()
        
        self.assertTrue(extractor.is_supported(Path('test.xlsx')))
        self.assertTrue(extractor.is_supported(Path('test.docx')))
        self.assertTrue(extractor.is_supported(Path('test.XLSX')))  # Case insensitive
        self.assertTrue(extractor.is_supported(Path('test.DOCX')))
        
        self.assertFalse(extractor.is_supported(Path('test.xls')))
        self.assertFalse(extractor.is_supported(Path('test.doc')))
        self.assertFalse(extractor.is_supported(Path('test.pdf')))
        self.assertFalse(extractor.is_supported(Path('test.txt')))
    
    def test_extract_xlsx(self):
        """Extract should route xlsx to ExcelExtractor."""
        extractor = OfficeExtractor()
        documents = extractor.extract(self.sample_xlsx)
        
        self.assertGreater(len(documents), 0)
        self.assertEqual(documents[0]['metadata']['doc_type'], 'xlsx')
    
    def test_extract_docx(self):
        """Extract should route docx to WordExtractor."""
        extractor = OfficeExtractor()
        documents = extractor.extract(self.sample_docx)
        
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]['metadata']['doc_type'], 'docx')
    
    def test_extract_unsupported(self):
        """Unsupported files should return error document."""
        extractor = OfficeExtractor()
        
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(b'plain text')
            temp_path = Path(f.name)
        
        try:
            documents = extractor.extract(temp_path)
            self.assertEqual(len(documents), 1)
            self.assertIsNotNone(documents[0]['error'])
            self.assertIn('Unsupported', documents[0]['error'])
        finally:
            temp_path.unlink()


class TestExcelCellParsing(unittest.TestCase):
    """Tests for Excel cell reference parsing."""
    
    def test_parse_simple_refs(self):
        """Parse simple cell references like A1, B2."""
        extractor = ExcelExtractor()
        
        self.assertEqual(extractor._parse_cell_ref('A1'), (0, 0))
        self.assertEqual(extractor._parse_cell_ref('B1'), (0, 1))
        self.assertEqual(extractor._parse_cell_ref('A2'), (1, 0))
        self.assertEqual(extractor._parse_cell_ref('Z1'), (0, 25))
    
    def test_parse_double_letter_refs(self):
        """Parse cell references like AA1, AB1."""
        extractor = ExcelExtractor()
        
        self.assertEqual(extractor._parse_cell_ref('AA1'), (0, 26))
        self.assertEqual(extractor._parse_cell_ref('AB1'), (0, 27))
        self.assertEqual(extractor._parse_cell_ref('AZ1'), (0, 51))
        self.assertEqual(extractor._parse_cell_ref('BA1'), (0, 52))


class TestWordHeadingDetection(unittest.TestCase):
    """Tests for Word heading style detection."""
    
    def test_heading_patterns(self):
        """Test heading style name pattern matching."""
        extractor = WordExtractor()
        
        # Standard headings
        self.assertEqual(extractor._get_heading_level('Heading 1'), 1)
        self.assertEqual(extractor._get_heading_level('Heading 2'), 2)
        self.assertEqual(extractor._get_heading_level('Heading 3'), 3)
        
        # Title/Subtitle
        self.assertEqual(extractor._get_heading_level('Title'), 1)
        self.assertEqual(extractor._get_heading_level('Subtitle'), 2)
        
        # Non-headings
        self.assertIsNone(extractor._get_heading_level('Normal'))
        self.assertIsNone(extractor._get_heading_level('Body Text'))
        self.assertIsNone(extractor._get_heading_level(''))


class TestExcelEmptyContent(unittest.TestCase):
    """Tests for handling empty Excel content."""
    
    def test_empty_sheet(self):
        """Empty sheets should be handled gracefully."""
        extractor = ExcelExtractor()
        
        # Create an xlsx with empty sheet
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            with zipfile.ZipFile(temp_path, 'w') as zf:
                content_types = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>'''
                zf.writestr('[Content_Types].xml', content_types)
                
                rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''
                zf.writestr('_rels/.rels', rels)
                
                workbook_rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>'''
                zf.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
                
                workbook = '''<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Empty" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>'''
                zf.writestr('xl/workbook.xml', workbook)
                
                sheet = '''<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData/>
</worksheet>'''
                zf.writestr('xl/worksheets/sheet1.xml', sheet)
            
            documents = extractor.extract_from_file(temp_path)
            self.assertEqual(len(documents), 1)
            self.assertIsNone(documents[0]['error'])
            self.assertEqual(documents[0]['text'], '')
        finally:
            temp_path.unlink()


if __name__ == '__main__':
    unittest.main()
