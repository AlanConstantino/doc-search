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
    
    def _extract_paragraphs(
        self,
        zf: zipfile.ZipFile,
        styles: Dict[str, str]
    ) -> Tuple[List[str], List[Tuple[int, str]], int]:
        """
        Extract paragraphs with heading detection.
        
        Returns:
            Tuple of (paragraphs, headings, word_count)
        """
        paragraphs = []
        headings = []
        word_count = 0
        w_ns = NAMESPACES['w']
        
        try:
            with zf.open('word/document.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                
                for para in root.iter(f'{{{w_ns}}}p'):
                    # Extract text from paragraph
                    para_text_parts = []
                    for elem in para.iter():
                        if elem.tag == f'{{{w_ns}}}t':
                            if elem.text:
                                para_text_parts.append(elem.text)
                        elif elem.tag == f'{{{w_ns}}}tab':
                            para_text_parts.append('\t')
                        elif elem.tag in (f'{{{w_ns}}}br', f'{{{w_ns}}}cr'):
                            para_text_parts.append('\n')
                    
                    text = ''.join(para_text_parts).strip()
                    if not text:
                        continue
                    
                    word_count += len(text.split())
                    
                    # Check if this is a heading
                    pPr = para.find(f'{{{w_ns}}}pPr')
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
