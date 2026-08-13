"""
Word (.docx) text extraction using pure Python standard library.

Extracts text content from Word documents with:
- Heading detection from Word styles
- Document properties (title, author, dates)
- Paragraph structure preserved
- Headers and footers included

Uses only zipfile and xml.etree.ElementTree - no external dependencies.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


# XML namespaces for Office Open XML (OOXML) format
NAMESPACES = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'dcterms': 'http://purl.org/dc/terms/',
}


class WordExtractor:
    """
    Extract text from Word .docx files using pure Python stdlib.
    
    Extracts:
    - Title from document properties or first heading
    - Headings from Word heading styles
    - Body text with paragraph structure preserved
    - Document metadata (author, dates, word count)
    - Headers and footers
    """
    
    # Heading style name patterns
    HEADING_PATTERNS = [
        (re.compile(r'^Heading\s*(\d+)$', re.I), lambda m: int(m.group(1))),
        (re.compile(r'^Title$', re.I), lambda m: 1),
        (re.compile(r'^Subtitle$', re.I), lambda m: 2),
        (re.compile(r'^Heading$', re.I), lambda m: 1),
        (re.compile(r'^TOC\s*Heading', re.I), lambda m: 1),
    ]
    
    def _qn(self, tag: str) -> str:
        """Convert namespace-prefixed tag to Clark notation."""
        if ':' not in tag:
            return tag
        prefix, local = tag.split(':', 1)
        uri = NAMESPACES.get(prefix, '')
        return f'{{{uri}}}{local}' if uri else tag
    
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
        """Extract core document properties (title, author, dates)."""
        props = {}
        try:
            with zf.open('docProps/core.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                
                # Title
                title = root.find(f'.//{{{NAMESPACES["dc"]}}}title')
                if title is not None and title.text:
                    props['title'] = title.text.strip()
                
                # Creator/Author
                creator = root.find(f'.//{{{NAMESPACES["dc"]}}}creator')
                if creator is not None and creator.text:
                    props['author'] = creator.text.strip()
                
                # Created date
                created = root.find(f'.//{{{NAMESPACES["dcterms"]}}}created')
                if created is not None and created.text:
                    props['created'] = created.text.strip()
                
                # Modified date
                modified = root.find(f'.//{{{NAMESPACES["dcterms"]}}}modified')
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
                
                w_ns = NAMESPACES['w']
                for style in root.findall(f'.//{{{w_ns}}}style'):
                    style_id = style.get(f'{{{w_ns}}}styleId')
                    name_elem = style.find(f'{{{w_ns}}}name')
                    if style_id and name_elem is not None:
                        name = name_elem.get(f'{{{w_ns}}}val', '')
                        if name:
                            styles[style_id] = name
        except (KeyError, ET.ParseError):
            pass
        
        return styles
    
    def _extract_text_from_xml(self, xml_content: bytes) -> str:
        """Extract text from a Word XML file (document, header, footer)."""
        text_parts = []
        w_ns = NAMESPACES['w']
        
        try:
            root = ET.fromstring(xml_content)
            
            for elem in root.iter():
                if elem.tag == f'{{{w_ns}}}t':
                    if elem.text:
                        text_parts.append(elem.text)
                elif elem.tag == f'{{{w_ns}}}tab':
                    text_parts.append('\t')
                elif elem.tag in (f'{{{w_ns}}}br', f'{{{w_ns}}}cr'):
                    text_parts.append('\n')
                elif elem.tag == f'{{{w_ns}}}p':
                    text_parts.append('\n\n')
        except ET.ParseError:
            pass
        
        return ''.join(text_parts).strip()
    
    def _get_relationships(self, zf: zipfile.ZipFile) -> Dict[str, str]:
        """
        Load document relationships (rId → target URL) for hyperlinks.
        
        Returns:
            Dict mapping relationship ID to target URL
        """
        rels = {}
        rels_path = 'word/_rels/document.xml.rels'
        if rels_path not in zf.namelist():
            return rels
        
        try:
            with zf.open(rels_path) as f:
                tree = ET.parse(f)
                root = tree.getroot()
                # Relationship namespace
                rel_ns = 'http://schemas.openxmlformats.org/package/2006/relationships'
                for rel in root.findall(f'{{{rel_ns}}}Relationship'):
                    rid = rel.get('Id', '')
                    target = rel.get('Target', '')
                    target_mode = rel.get('TargetMode', '')
                    # Only include external hyperlinks
                    if target_mode == 'External' and rid:
                        rels[rid] = target
        except (KeyError, ET.ParseError):
            pass
        
        return rels
    
    def _extract_paragraph_text(
        self,
        para,
        rels: Dict[str, str]
    ) -> str:
        """
        Extract text from a single paragraph element, including hyperlink URLs.
        
        Args:
            para: XML paragraph element (<w:p>)
            rels: Relationship ID → URL map for hyperlinks
            
        Returns:
            Extracted text string
        """
        w_ns = NAMESPACES['w']
        parts = []
        
        for child in para:
            if child.tag == f'{{{w_ns}}}hyperlink':
                # Extract hyperlink display text
                link_text_parts = []
                for elem in child.iter():
                    if elem.tag == f'{{{w_ns}}}t' and elem.text:
                        link_text_parts.append(elem.text)
                link_text = ''.join(link_text_parts)
                
                # Get the URL from relationships
                r_ns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
                rid = child.get(f'{{{r_ns}}}id', '')
                url = rels.get(rid, '')
                
                if link_text:
                    if url and url.lower() != link_text.lower():
                        # Append URL if it's different from display text
                        parts.append(f'{link_text} ({url})')
                    else:
                        parts.append(link_text)
            elif child.tag == f'{{{w_ns}}}r':
                # Regular run
                for elem in child.iter():
                    if elem.tag == f'{{{w_ns}}}t' and elem.text:
                        parts.append(elem.text)
                    elif elem.tag == f'{{{w_ns}}}tab':
                        parts.append('\t')
                    elif elem.tag in (f'{{{w_ns}}}br', f'{{{w_ns}}}cr'):
                        parts.append('\n')
        
        return ''.join(parts).strip()
    
    def _extract_table(
        self,
        tbl,
        rels: Dict[str, str]
    ) -> Tuple[str, List[Tuple[int, str]], int]:
        """
        Extract structured text from a Word table element.
        
        Args:
            tbl: XML table element (<w:tbl>)
            rels: Relationship ID → URL map for hyperlinks
            
        Returns:
            Tuple of (formatted_text, headings, word_count)
        """
        w_ns = NAMESPACES['w']
        rows = []
        
        for tr in tbl.findall(f'{{{w_ns}}}tr'):
            cells = []
            for tc in tr.findall(f'{{{w_ns}}}tc'):
                # A table cell can contain multiple paragraphs
                cell_parts = []
                for para in tc.findall(f'{{{w_ns}}}p'):
                    text = self._extract_paragraph_text(para, rels)
                    if text:
                        cell_parts.append(text)
                cells.append(' '.join(cell_parts))
            rows.append(cells)
        
        if not rows:
            return '', [], 0
        
        word_count = sum(len(cell.split()) for row in rows for cell in row if cell)
        headings = []
        
        # Check if first row looks like headers
        # (has content and subsequent rows have similar column count)
        headers = None
        if len(rows) >= 2:
            first_row = rows[0]
            if any(cell.strip() for cell in first_row):
                # Use first row as headers
                headers = first_row
                # Add a heading for the table using first header
                first_header = next((h for h in headers if h.strip()), None)
                if first_header:
                    headings.append((3, f'Table: {first_header}'))
        
        # Format rows
        lines = []
        start_row = 1 if headers else 0
        for row in rows[start_row:]:
            if not any(cell.strip() for cell in row):
                continue
            
            if headers:
                # Format as "Header: value" pairs
                parts = []
                for i, cell in enumerate(row):
                    if cell.strip():
                        header = headers[i].strip() if i < len(headers) and headers[i].strip() else f'Col{i+1}'
                        parts.append(f'{header}: {cell.strip()}')
                if parts:
                    lines.append(', '.join(parts))
            else:
                # Format as pipe-separated values
                non_empty = [cell.strip() for cell in row if cell.strip()]
                if non_empty:
                    lines.append(' | '.join(non_empty))
        
        return '\n'.join(lines), headings, word_count
    
    def _extract_paragraphs(
        self,
        zf: zipfile.ZipFile,
        styles: Dict[str, str]
    ) -> Tuple[List[str], List[Tuple[int, str]], int]:
        """
        Extract paragraphs, tables, and hyperlinks with heading detection.
        
        Walks the document body's direct children to properly handle
        tables as distinct elements (instead of iterating all <w:p>
        elements which mashes table cells together).
        
        Returns:
            Tuple of (paragraphs, headings, word_count)
        """
        paragraphs = []
        headings = []
        word_count = 0
        w_ns = NAMESPACES['w']
        
        # Load relationships for hyperlink resolution
        rels = self._get_relationships(zf)
        
        try:
            with zf.open('word/document.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                
                # Find the document body
                body = root.find(f'{{{w_ns}}}body')
                if body is None:
                    # Fallback: iterate all paragraphs
                    body = root
                    children = list(root.iter(f'{{{w_ns}}}p'))
                    for para in children:
                        text = self._extract_paragraph_text(para, rels)
                        if text:
                            word_count += len(text.split())
                            paragraphs.append(text)
                    return paragraphs, headings, word_count
                
                # Walk body's direct children to distinguish paragraphs from tables
                for child in body:
                    if child.tag == f'{{{w_ns}}}tbl':
                        # Table element — extract with structure
                        table_text, table_headings, table_words = self._extract_table(child, rels)
                        if table_text:
                            paragraphs.append(table_text)
                            headings.extend(table_headings)
                            word_count += table_words
                    
                    elif child.tag == f'{{{w_ns}}}p':
                        # Regular paragraph
                        text = self._extract_paragraph_text(child, rels)
                        if not text:
                            continue
                        
                        word_count += len(text.split())
                        
                        # Check if this is a heading
                        pPr = child.find(f'{{{w_ns}}}pPr')
                        style_id = None
                        if pPr is not None:
                            pStyle = pPr.find(f'{{{w_ns}}}pStyle')
                            if pStyle is not None:
                                style_id = pStyle.get(f'{{{w_ns}}}val')
                        
                        style_name = styles.get(style_id, style_id or '')
                        heading_level = self._get_heading_level(style_name)
                        
                        if heading_level is not None:
                            headings.append((heading_level, text))
                        
                        paragraphs.append(text)
                    
                    # Skip other element types (sdt, bookmarkStart, etc.)
                    
        except (KeyError, ET.ParseError):
            pass
        
        return paragraphs, headings, word_count
    
    def _extract_headers_footers(self, zf: zipfile.ZipFile) -> Tuple[str, str]:
        """Extract text from headers and footers."""
        header_text = []
        footer_text = []
        
        for name in zf.namelist():
            if re.match(r'word/header\d*\.xml', name):
                try:
                    text = self._extract_text_from_xml(zf.read(name))
                    if text:
                        header_text.append(text)
                except (KeyError, ET.ParseError):
                    pass
            elif re.match(r'word/footer\d*\.xml', name):
                try:
                    text = self._extract_text_from_xml(zf.read(name))
                    if text:
                        footer_text.append(text)
                except (KeyError, ET.ParseError):
                    pass
        
        return '\n'.join(header_text), '\n'.join(footer_text)
    
    def extract_from_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract document from a Word file.
        
        Args:
            file_path: Path to the .docx file
            
        Returns:
            Document dict with url, title, text, headings, metadata, error
        """
        file_path = Path(file_path)
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
                
                # Extract paragraphs and headings
                paragraphs, headings, word_count = self._extract_paragraphs(zf, styles)
                result['headings'] = headings
                result['metadata']['word_count'] = word_count
                
                # Extract headers and footers
                header_text, footer_text = self._extract_headers_footers(zf)
                
                # Combine all text
                all_text = []
                if header_text:
                    all_text.append(header_text)
                all_text.extend(paragraphs)
                if footer_text:
                    all_text.append(footer_text)
                
                result['text'] = '\n\n'.join(all_text)
                
                # Determine title (priority: metadata > first H1 > first heading > filename)
                if not result['title']:
                    h1_headings = [h for h in headings if h[0] == 1]
                    if h1_headings:
                        result['title'] = h1_headings[0][1]
                    elif headings:
                        result['title'] = headings[0][1]
                    else:
                        result['title'] = file_path.stem
                
        except zipfile.BadZipFile:
            result['error'] = 'Invalid or corrupted docx file'
        except KeyError as e:
            result['error'] = f'Missing required file in docx: {e}'
        except ET.ParseError as e:
            result['error'] = f'XML parse error: {e}'
        except FileNotFoundError:
            result['error'] = f'File not found: {file_path}'
        except Exception as e:
            result['error'] = f'Extraction error: {e}'
        
        return result
    
    def extract(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Extract document from a Word file.
        
        Returns a list for consistency with ExcelExtractor (which returns
        multiple documents for multiple sheets).
        """
        return [self.extract_from_file(file_path)]


def extract_word_text(file_path: str, **kwargs) -> str:
    """
    Convenience function to extract just the text from a Word file.
    
    Args:
        file_path: Path to Word file
        
    Returns:
        Extracted text or empty string on failure
    """
    extractor = WordExtractor()
    result = extractor.extract_from_file(Path(file_path))
    return result.get('text', '') if not result.get('error') else ''


# CLI for testing
if __name__ == '__main__':
    import argparse
    import json
    import sys
    
    parser = argparse.ArgumentParser(description='Extract text from Word files')
    parser.add_argument('file', help='Path to .docx file')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--headings', action='store_true', help='Show detected headings')
    args = parser.parse_args()
    
    extractor = WordExtractor()
    file_path = Path(args.file)
    
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    
    result = extractor.extract_from_file(file_path)
    
    if args.json:
        # Convert headings tuples to lists for JSON
        result['headings'] = [list(h) for h in result['headings']]
        print(json.dumps(result, indent=2))
    else:
        if result['error']:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
        
        print(f"Title: {result['title']}")
        print(f"URL: {result['url']}")
        
        meta = result['metadata']
        if 'author' in meta:
            print(f"Author: {meta['author']}")
        if 'word_count' in meta:
            print(f"Words: {meta['word_count']}")
        if 'created' in meta:
            print(f"Created: {meta['created']}")
        
        if args.headings or result['headings']:
            print(f"\nHeadings ({len(result['headings'])}):")
            for level, text in result['headings'][:20]:
                indent = "  " * (level - 1)
                print(f"  {indent}[H{level}] {text[:80]}")
            if len(result['headings']) > 20:
                print(f"  ... and {len(result['headings']) - 20} more")
        
        print(f"\n{'-'*50}\n")
        preview = result['text'][:2000]
        print(preview)
        if len(result['text']) > 2000:
            print(f"\n... ({len(result['text']) - 2000} more characters)")
