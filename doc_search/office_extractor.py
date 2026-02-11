"""
Office document extraction using pure Python standard library.

Extracts text from:
- Excel (.xlsx) - ZIP containing XML worksheets
- Word (.docx) - ZIP containing XML document

Maintains zero external dependencies by parsing Open XML formats directly.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from urllib.parse import quote


# XML namespaces for Office Open XML formats
NAMESPACES = {
    # Word namespaces
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'dcterms': 'http://purl.org/dc/terms/',
    # Excel namespaces
    'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'xr': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}


class ExcelExtractor:
    """
    Extract text from Excel .xlsx files.
    
    Creates one document per worksheet with:
    - Header row detection for context-aware text extraction
    - Cell values extracted row-by-row
    - Metadata including row/column counts
    """
    
    def __init__(self, first_row_is_header: bool = True):
        """
        Initialize Excel extractor.
        
        Args:
            first_row_is_header: If True, treat first row as column headers
        """
        self.first_row_is_header = first_row_is_header
    
    def _get_shared_strings(self, zf: zipfile.ZipFile) -> List[str]:
        """Extract shared strings table from xlsx."""
        strings = []
        try:
            with zf.open('xl/sharedStrings.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                # Find all string items
                for si in root.findall('.//{%s}si' % NAMESPACES['x']):
                    # Get text from <t> elements (may be nested in <r> runs)
                    text_parts = []
                    for t in si.iter('{%s}t' % NAMESPACES['x']):
                        if t.text:
                            text_parts.append(t.text)
                    strings.append(''.join(text_parts))
        except KeyError:
            # No shared strings file
            pass
        except ET.ParseError:
            pass
        return strings
    
    def _get_sheet_names(self, zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
        """Get list of (sheet_name, sheet_path) tuples."""
        sheets = []
        try:
            with zf.open('xl/workbook.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                for sheet in root.findall('.//{%s}sheet' % NAMESPACES['x']):
                    name = sheet.get('name', 'Sheet')
                    sheet_id = sheet.get('{%s}id' % NAMESPACES['xr'])
                    sheets.append((name, sheet_id))
        except (KeyError, ET.ParseError):
            pass
        
        # Map relationship IDs to file paths
        rels = {}
        try:
            with zf.open('xl/_rels/workbook.xml.rels') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                for rel in root.findall('.//{%s}Relationship' % NAMESPACES['r'].replace('officeDocument', 'package')):
                    rel_id = rel.get('Id')
                    target = rel.get('Target')
                    if rel_id and target:
                        rels[rel_id] = target
        except (KeyError, ET.ParseError):
            pass
        
        # Match sheet names to paths
        result = []
        for name, sheet_id in sheets:
            if sheet_id in rels:
                path = rels[sheet_id]
                if not path.startswith('/'):
                    path = 'xl/' + path
                else:
                    path = path[1:]  # Remove leading slash
                result.append((name, path))
            else:
                # Fallback: try numbered sheets
                idx = len(result) + 1
                result.append((name, f'xl/worksheets/sheet{idx}.xml'))
        
        return result
    
    def _parse_cell_ref(self, cell_ref: str) -> Tuple[int, int]:
        """Parse cell reference like 'A1' into (row, col) 0-indexed."""
        match = re.match(r'([A-Z]+)(\d+)', cell_ref)
        if not match:
            return (0, 0)
        
        col_str, row_str = match.groups()
        row = int(row_str) - 1
        
        # Convert column letters to number (A=0, B=1, ..., Z=25, AA=26, etc.)
        col = 0
        for char in col_str:
            col = col * 26 + (ord(char) - ord('A') + 1)
        col -= 1
        
        return (row, col)
    
    def _extract_sheet(
        self,
        zf: zipfile.ZipFile,
        sheet_path: str,
        shared_strings: List[str]
    ) -> Dict[str, Any]:
        """Extract data from a single worksheet."""
        result = {
            'rows': [],
            'row_count': 0,
            'col_count': 0,
            'error': None
        }
        
        try:
            with zf.open(sheet_path) as f:
                tree = ET.parse(f)
                root = tree.getroot()
                
                # Find all rows
                rows_data = {}
                max_col = 0
                
                for row in root.findall('.//{%s}row' % NAMESPACES['x']):
                    row_num = int(row.get('r', 0))
                    cells = {}
                    
                    for cell in row.findall('{%s}c' % NAMESPACES['x']):
                        cell_ref = cell.get('r', '')
                        cell_type = cell.get('t', '')
                        
                        # Get cell value
                        value_elem = cell.find('{%s}v' % NAMESPACES['x'])
                        value = ''
                        
                        if value_elem is not None and value_elem.text:
                            if cell_type == 's':
                                # Shared string reference
                                try:
                                    idx = int(value_elem.text)
                                    if 0 <= idx < len(shared_strings):
                                        value = shared_strings[idx]
                                except (ValueError, IndexError):
                                    value = value_elem.text
                            elif cell_type == 'b':
                                # Boolean
                                value = 'TRUE' if value_elem.text == '1' else 'FALSE'
                            else:
                                # Number or other
                                value = value_elem.text
                        else:
                            # Check for inline string
                            inline = cell.find('.//{%s}t' % NAMESPACES['x'])
                            if inline is not None and inline.text:
                                value = inline.text
                        
                        if value and cell_ref:
                            row_idx, col_idx = self._parse_cell_ref(cell_ref)
                            cells[col_idx] = value.strip()
                            max_col = max(max_col, col_idx)
                    
                    if cells:
                        rows_data[row_num - 1] = cells
                
                # Convert to list of lists
                if rows_data:
                    max_row = max(rows_data.keys())
                    for row_idx in range(max_row + 1):
                        row_cells = rows_data.get(row_idx, {})
                        row_list = []
                        for col_idx in range(max_col + 1):
                            row_list.append(row_cells.get(col_idx, ''))
                        result['rows'].append(row_list)
                
                result['row_count'] = len(result['rows'])
                result['col_count'] = max_col + 1 if result['rows'] else 0
                
        except KeyError:
            result['error'] = f"Sheet not found: {sheet_path}"
        except ET.ParseError as e:
            result['error'] = f"XML parse error: {e}"
        except Exception as e:
            result['error'] = f"Extraction error: {e}"
        
        return result
    
    def _format_rows_with_headers(
        self,
        rows: List[List[str]],
        headers: Optional[List[str]] = None
    ) -> str:
        """Format rows as text, optionally with header context."""
        if not rows:
            return ''
        
        lines = []
        start_row = 0
        
        if headers:
            start_row = 1
        
        for row in rows[start_row:]:
            if not any(cell.strip() for cell in row):
                continue  # Skip empty rows
            
            if headers:
                # Format with headers: "Header1: value1, Header2: value2"
                parts = []
                for i, cell in enumerate(row):
                    if cell.strip():
                        header = headers[i] if i < len(headers) and headers[i] else f"Col{i+1}"
                        parts.append(f"{header}: {cell}")
                if parts:
                    lines.append(', '.join(parts))
            else:
                # Format without headers: "value1 | value2 | value3"
                non_empty = [cell for cell in row if cell.strip()]
                if non_empty:
                    lines.append(' | '.join(non_empty))
        
        return '\n'.join(lines)
    
    def extract_from_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Extract documents from an Excel file (one per sheet).
        
        Args:
            file_path: Path to the .xlsx file
            
        Returns:
            List of document dicts, one per sheet
        """
        documents = []
        
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                shared_strings = self._get_shared_strings(zf)
                sheets = self._get_sheet_names(zf)
                
                for idx, (sheet_name, sheet_path) in enumerate(sheets):
                    sheet_data = self._extract_sheet(zf, sheet_path, shared_strings)
                    
                    if sheet_data['error']:
                        documents.append({
                            'url': f"file://{file_path}#{quote(sheet_name)}",
                            'title': f"{file_path.name} - {sheet_name}",
                            'text': '',
                            'headings': [],
                            'error': sheet_data['error'],
                            'metadata': {
                                'doc_type': 'xlsx',
                                'sheet_name': sheet_name,
                                'sheet_index': idx,
                                'workbook': file_path.name,
                                'file_path': str(file_path.absolute()),
                            }
                        })
                        continue
                    
                    # Determine headers
                    headers = None
                    if self.first_row_is_header and sheet_data['rows']:
                        headers = sheet_data['rows'][0]
                    
                    # Format text content
                    text = self._format_rows_with_headers(sheet_data['rows'], headers)
                    
                    # Create headings list (using headers as H2)
                    headings = []
                    if headers:
                        for h in headers:
                            if h.strip():
                                headings.append((2, h.strip()))
                    
                    documents.append({
                        'url': f"file://{file_path.absolute()}#{quote(sheet_name)}",
                        'title': f"{file_path.name} - {sheet_name}",
                        'text': text,
                        'headings': headings,
                        'error': None,
                        'metadata': {
                            'doc_type': 'xlsx',
                            'sheet_name': sheet_name,
                            'sheet_index': idx,
                            'workbook': file_path.name,
                            'row_count': sheet_data['row_count'],
                            'col_count': sheet_data['col_count'],
                            'file_path': str(file_path.absolute()),
                        }
                    })
                    
        except zipfile.BadZipFile:
            documents.append({
                'url': f"file://{file_path}",
                'title': file_path.name,
                'text': '',
                'headings': [],
                'error': 'Invalid or corrupted xlsx file',
                'metadata': {'doc_type': 'xlsx', 'file_path': str(file_path)}
            })
        except Exception as e:
            documents.append({
                'url': f"file://{file_path}",
                'title': file_path.name,
                'text': '',
                'headings': [],
                'error': f'Extraction error: {e}',
                'metadata': {'doc_type': 'xlsx', 'file_path': str(file_path)}
            })
        
        return documents


class WordExtractor:
    """
    Extract text from Word .docx files.
    
    Extracts:
    - Title from document properties or first heading
    - Headings from Word heading styles
    - Body text with paragraph structure preserved
    - Document metadata (author, dates, word count)
    """
    
    # Heading style name patterns
    HEADING_PATTERNS = [
        (re.compile(r'^Heading\s*(\d+)$', re.I), lambda m: int(m.group(1))),
        (re.compile(r'^Title$', re.I), lambda m: 1),
        (re.compile(r'^Subtitle$', re.I), lambda m: 2),
        (re.compile(r'^Heading$', re.I), lambda m: 1),
    ]
    
    def _get_heading_level(self, style_name: str) -> Optional[int]:
        """Get heading level from style name (1-6) or None if not a heading."""
        if not style_name:
            return None
        
        for pattern, level_fn in self.HEADING_PATTERNS:
            match = pattern.match(style_name)
            if match:
                level = level_fn(match)
                return min(max(level, 1), 6)
        
        return None
    
    def _get_core_properties(self, zf: zipfile.ZipFile) -> Dict[str, str]:
        """Extract core document properties."""
        props = {}
        try:
            with zf.open('docProps/core.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                
                # Title
                title = root.find('.//{%s}title' % NAMESPACES['dc'])
                if title is not None and title.text:
                    props['title'] = title.text.strip()
                
                # Creator/Author
                creator = root.find('.//{%s}creator' % NAMESPACES['dc'])
                if creator is not None and creator.text:
                    props['author'] = creator.text.strip()
                
                # Created date
                created = root.find('.//{%s}created' % NAMESPACES['dcterms'])
                if created is not None and created.text:
                    props['created'] = created.text.strip()
                
                # Modified date
                modified = root.find('.//{%s}modified' % NAMESPACES['dcterms'])
                if modified is not None and modified.text:
                    props['modified'] = modified.text.strip()
                    
        except (KeyError, ET.ParseError):
            pass
        
        return props
    
    def _get_styles(self, zf: zipfile.ZipFile) -> Dict[str, str]:
        """Extract style ID to style name mapping."""
        styles = {}
        try:
            with zf.open('word/styles.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                
                for style in root.findall('.//{%s}style' % NAMESPACES['w']):
                    style_id = style.get('{%s}styleId' % NAMESPACES['w'])
                    name_elem = style.find('{%s}name' % NAMESPACES['w'])
                    if style_id and name_elem is not None:
                        name = name_elem.get('{%s}val' % NAMESPACES['w'], '')
                        if name:
                            styles[style_id] = name
        except (KeyError, ET.ParseError):
            pass
        
        return styles
    
    def _extract_paragraph_text(self, para: ET.Element) -> str:
        """Extract all text from a paragraph element."""
        texts = []
        for t in para.iter('{%s}t' % NAMESPACES['w']):
            if t.text:
                texts.append(t.text)
        return ''.join(texts)
    
    def _get_paragraph_style(self, para: ET.Element) -> Optional[str]:
        """Get the style ID of a paragraph."""
        pPr = para.find('{%s}pPr' % NAMESPACES['w'])
        if pPr is not None:
            pStyle = pPr.find('{%s}pStyle' % NAMESPACES['w'])
            if pStyle is not None:
                return pStyle.get('{%s}val' % NAMESPACES['w'])
        return None
    
    def extract_from_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract document from a Word file.
        
        Args:
            file_path: Path to the .docx file
            
        Returns:
            Document dict with url, title, text, headings, metadata, error
        """
        result = {
            'url': f"file://{file_path.absolute()}",
            'title': '',
            'text': '',
            'headings': [],
            'metadata': {
                'doc_type': 'docx',
                'file_path': str(file_path.absolute()),
            },
            'error': None
        }
        
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                # Get document properties
                props = self._get_core_properties(zf)
                result['metadata'].update(props)
                if 'title' in props:
                    result['title'] = props['title']
                
                # Get styles for heading detection
                styles = self._get_styles(zf)
                
                # Parse main document
                paragraphs = []
                headings = []
                first_heading = None
                word_count = 0
                
                with zf.open('word/document.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    
                    for para in root.iter('{%s}p' % NAMESPACES['w']):
                        text = self._extract_paragraph_text(para)
                        if not text.strip():
                            continue
                        
                        word_count += len(text.split())
                        
                        # Check if this is a heading
                        style_id = self._get_paragraph_style(para)
                        style_name = styles.get(style_id, style_id or '')
                        heading_level = self._get_heading_level(style_name)
                        
                        if heading_level is not None:
                            headings.append((heading_level, text.strip()))
                            if first_heading is None:
                                first_heading = text.strip()
                            paragraphs.append(text.strip())
                        else:
                            paragraphs.append(text.strip())
                
                result['text'] = '\n\n'.join(paragraphs)
                result['headings'] = headings
                result['metadata']['word_count'] = word_count
                
                # Determine title (priority: metadata > first H1 > first heading > filename)
                if not result['title']:
                    h1_headings = [h for h in headings if h[0] == 1]
                    if h1_headings:
                        result['title'] = h1_headings[0][1]
                    elif first_heading:
                        result['title'] = first_heading
                    else:
                        result['title'] = file_path.stem
                
        except zipfile.BadZipFile:
            result['error'] = 'Invalid or corrupted docx file'
        except KeyError as e:
            result['error'] = f'Missing required file in docx: {e}'
        except ET.ParseError as e:
            result['error'] = f'XML parse error: {e}'
        except Exception as e:
            result['error'] = f'Extraction error: {e}'
        
        return result


class OfficeExtractor:
    """
    Unified extractor for Office documents.
    
    Supports:
    - .xlsx (Excel) - via ExcelExtractor
    - .docx (Word) - via WordExtractor
    """
    
    SUPPORTED_EXTENSIONS = {'.xlsx', '.docx'}
    
    def __init__(self, first_row_is_header: bool = True):
        """
        Initialize Office extractor.
        
        Args:
            first_row_is_header: For Excel files, treat first row as headers
        """
        self.excel_extractor = ExcelExtractor(first_row_is_header=first_row_is_header)
        self.word_extractor = WordExtractor()
    
    def is_supported(self, file_path: Path) -> bool:
        """Check if file extension is supported."""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS
    
    def extract(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Extract documents from an Office file.
        
        Args:
            file_path: Path to the Office file
            
        Returns:
            List of document dicts (multiple for Excel sheets, one for Word)
        """
        file_path = Path(file_path)
        ext = file_path.suffix.lower()
        
        if ext == '.xlsx':
            return self.excel_extractor.extract_from_file(file_path)
        elif ext == '.docx':
            return [self.word_extractor.extract_from_file(file_path)]
        else:
            return [{
                'url': f"file://{file_path}",
                'title': file_path.name,
                'text': '',
                'headings': [],
                'error': f'Unsupported file type: {ext}',
                'metadata': {'file_path': str(file_path)}
            }]


# CLI for testing
if __name__ == '__main__':
    import argparse
    import json
    import sys
    
    parser = argparse.ArgumentParser(description='Extract text from Office documents')
    parser.add_argument('file', help='Path to .xlsx or .docx file')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--no-headers', action='store_true', 
                        help='Do not treat first Excel row as headers')
    args = parser.parse_args()
    
    extractor = OfficeExtractor(first_row_is_header=not args.no_headers)
    file_path = Path(args.file)
    
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    
    if not extractor.is_supported(file_path):
        print(f"Error: Unsupported file type: {file_path.suffix}", file=sys.stderr)
        sys.exit(1)
    
    documents = extractor.extract(file_path)
    
    if args.json:
        # Convert headings tuples to lists for JSON
        for doc in documents:
            doc['headings'] = [list(h) for h in doc['headings']]
        print(json.dumps(documents, indent=2))
    else:
        for doc in documents:
            if doc['error']:
                print(f"Error: {doc['error']}", file=sys.stderr)
                continue
            
            print(f"Title: {doc['title']}")
            print(f"URL: {doc['url']}")
            
            if doc.get('metadata'):
                meta = doc['metadata']
                if 'sheet_name' in meta:
                    print(f"Sheet: {meta['sheet_name']} ({meta['row_count']} rows, {meta['col_count']} cols)")
                if 'word_count' in meta:
                    print(f"Words: {meta['word_count']}")
                if 'author' in meta:
                    print(f"Author: {meta['author']}")
            
            if doc['headings']:
                print(f"\nHeadings ({len(doc['headings'])}):")
                for level, text in doc['headings'][:10]:
                    indent = "  " * (level - 1)
                    print(f"  {indent}[H{level}] {text[:60]}")
                if len(doc['headings']) > 10:
                    print(f"  ... and {len(doc['headings']) - 10} more")
            
            print(f"\n{'-'*50}\n")
            preview = doc['text'][:1500]
            print(preview)
            if len(doc['text']) > 1500:
                print(f"\n... ({len(doc['text']) - 1500} more characters)")
            print()
