"""
PowerPoint (.pptx) text extraction using pure Python.

A .pptx file is a ZIP archive containing XML. This module parses the
slide XML directly using only stdlib (zipfile + xml.etree.ElementTree),
so no third-party dependencies are needed.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# OpenXML namespaces
_NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
}


def _get_text_from_element(el: ET.Element) -> str:
    """Recursively extract all text from <a:t> elements under *el*."""
    parts = []
    for t in el.iter(f'{{{_NS["a"]}}}t'):
        if t.text:
            parts.append(t.text)
    return ''.join(parts)


def _extract_table_text(shape_tree: ET.Element) -> List[str]:
    """Extract rows from <a:tbl> tables inside a shape tree."""
    rows_text = []
    for tbl in shape_tree.iter(f'{{{_NS["a"]}}}tbl'):
        for tr in tbl.iter(f'{{{_NS["a"]}}}tr'):
            cells = []
            for tc in tr.iter(f'{{{_NS["a"]}}}tc'):
                cell_text = _get_text_from_element(tc).strip()
                if cell_text:
                    cells.append(cell_text)
            if cells:
                rows_text.append(' | '.join(cells))
    return rows_text


class PPTXExtractor:
    """Extract text and metadata from PowerPoint files (pure Python)."""

    def extract(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Extract text from a PowerPoint file.

        Returns one document per presentation (all slides combined).

        Args:
            file_path: Path to the .pptx file

        Returns:
            List with one dict containing url, title, text, headings, metadata
        """
        file_path = Path(file_path)

        try:
            zf = zipfile.ZipFile(file_path)
        except Exception as e:
            return [{'error': f'Failed to open PowerPoint file: {e}'}]

        with zf:
            # --- core properties (title, author) ---
            title, author = '', ''
            if 'docProps/core.xml' in zf.namelist():
                try:
                    core = ET.fromstring(zf.read('docProps/core.xml'))
                    dc_title = core.find('dc:title', _NS)
                    if dc_title is not None and dc_title.text:
                        title = dc_title.text.strip()
                    dc_creator = core.find('dc:creator', _NS)
                    if dc_creator is not None and dc_creator.text:
                        author = dc_creator.text.strip()
                except Exception:
                    pass

            # --- discover slides via presentation.xml rels ---
            slide_paths = self._get_slide_paths(zf)
            total_slides = len(slide_paths)

            # --- per-slide relationships (for notes) ---
            slides_text = []
            headings: List[Tuple[int, str]] = []

            for slide_num, slide_path in enumerate(slide_paths, 1):
                try:
                    slide_xml = ET.fromstring(zf.read(slide_path))
                except Exception:
                    continue

                slide_parts: List[str] = []
                slide_title: Optional[str] = None

                # Shape tree lives under p:cSld/p:spTree
                sp_tree = slide_xml.find('.//p:cSld/p:spTree', _NS)
                if sp_tree is not None:
                    for sp in sp_tree.findall('p:sp', _NS):
                        # Check if this is the title placeholder
                        nv = sp.find('p:nvSpPr/p:nvPr/p:ph', _NS)
                        is_title = False
                        if nv is not None:
                            ph_type = nv.get('type', '')
                            ph_idx = nv.get('idx', '0')
                            if ph_type in ('title', 'ctrTitle') or (ph_type == '' and ph_idx == '0'):
                                is_title = True

                        text = _get_text_from_element(sp).strip()
                        if text:
                            if is_title and not slide_title:
                                slide_title = text
                            slide_parts.append(text)

                    # Tables
                    for gf in sp_tree.iter(f'{{{_NS["p"]}}}graphicFrame'):
                        slide_parts.extend(_extract_table_text(gf))

                # --- notes ---
                notes_text = self._get_notes(zf, slide_path)
                if notes_text:
                    slide_parts.append(f"Notes: {notes_text}")

                if slide_title:
                    headings.append((2, slide_title))
                    if not title and slide_num == 1:
                        title = slide_title

                if slide_parts:
                    header = f"Slide {slide_num}"
                    if slide_title:
                        header += f": {slide_title}"
                    slides_text.append(header + "\n" + "\n".join(slide_parts))

        full_text = "\n\n".join(slides_text)

        # Clean control characters
        full_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', full_text)

        if not title:
            title = file_path.stem

        return [{
            'url': file_path.as_uri(),
            'title': title,
            'text': full_text,
            'headings': headings,
            'metadata': {
                'doc_type': 'pptx',
                'total_slides': total_slides,
                'author': author,
            },
        }]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_slide_paths(zf: zipfile.ZipFile) -> List[str]:
        """Return slide XML paths in order from presentation.xml.rels."""
        rels_path = 'ppt/_rels/presentation.xml.rels'
        if rels_path not in zf.namelist():
            # Fallback: glob for slide files and sort
            slides = sorted(
                n for n in zf.namelist()
                if re.match(r'ppt/slides/slide\d+\.xml$', n)
            )
            return slides

        try:
            rels = ET.fromstring(zf.read(rels_path))
        except Exception:
            return []

        slide_rels = []
        for rel in rels.findall(f'{{{_NS["rel"]}}}Relationship'):
            target = rel.get('Target', '')
            if target.startswith('slides/slide'):
                # Extract slide number for sorting
                m = re.search(r'slide(\d+)\.xml', target)
                num = int(m.group(1)) if m else 0
                slide_rels.append((num, f'ppt/{target}'))

        slide_rels.sort(key=lambda x: x[0])
        return [path for _, path in slide_rels]

    @staticmethod
    def _get_notes(zf: zipfile.ZipFile, slide_path: str) -> str:
        """Extract notes text for a given slide path."""
        # Notes relationship lives in slide rels
        # e.g. ppt/slides/_rels/slide1.xml.rels -> ../notesSlides/notesSlide1.xml
        slide_name = Path(slide_path).name  # slide1.xml
        rels_path = f'ppt/slides/_rels/{slide_name}.rels'
        if rels_path not in zf.namelist():
            return ''

        try:
            rels = ET.fromstring(zf.read(rels_path))
        except Exception:
            return ''

        for rel in rels.findall(f'{{{_NS["rel"]}}}Relationship'):
            target = rel.get('Target', '')
            if 'notesSlide' in target:
                # Resolve relative path
                notes_path = f'ppt/notesSlides/{Path(target).name}'
                if notes_path in zf.namelist():
                    try:
                        notes_xml = ET.fromstring(zf.read(notes_path))
                        text = _get_text_from_element(notes_xml).strip()
                        return text
                    except Exception:
                        pass
        return ''
