#!/usr/bin/env python3
"""
Create test fixtures for Word extractor tests.
Creates minimal valid docx files using zipfile + XML.
"""

import zipfile
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent


def create_sample_docx():
    """Create a sample Word document with headings."""
    docx_path = FIXTURE_DIR / 'sample.docx'
    
    with zipfile.ZipFile(docx_path, 'w') as zf:
        # [Content_Types].xml
        content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>'''
        zf.writestr('[Content_Types].xml', content_types)
        
        # _rels/.rels
        rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>'''
        zf.writestr('_rels/.rels', rels)
        
        # word/_rels/document.xml.rels
        doc_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''
        zf.writestr('word/_rels/document.xml.rels', doc_rels)
        
        # word/document.xml
        document = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr>
        <w:pStyle w:val="Heading1"/>
      </w:pPr>
      <w:r>
        <w:t>Introduction</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:r>
        <w:t>This is the first paragraph of the document. It contains some sample text for testing purposes.</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:pPr>
        <w:pStyle w:val="Heading2"/>
      </w:pPr>
      <w:r>
        <w:t>Methods</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:r>
        <w:t>This section describes the methods used in our analysis.</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:pPr>
        <w:pStyle w:val="Heading2"/>
      </w:pPr>
      <w:r>
        <w:t>Results</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:r>
        <w:t>Here are the results of our study.</w:t>
      </w:r>
    </w:p>
  </w:body>
</w:document>'''
        zf.writestr('word/document.xml', document)
        
        # word/styles.xml
        styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="Heading 1"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="Heading 2"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="Heading 3"/>
  </w:style>
</w:styles>'''
        zf.writestr('word/styles.xml', styles)
        
        # docProps/core.xml
        core = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/">
  <dc:title>Test Document</dc:title>
  <dc:creator>Test Author</dc:creator>
  <dcterms:created>2024-01-15T10:30:00Z</dcterms:created>
  <dcterms:modified>2024-02-01T14:22:00Z</dcterms:modified>
</cp:coreProperties>'''
        zf.writestr('docProps/core.xml', core)
    
    print(f"Created: {docx_path}")


def create_no_metadata_docx():
    """Create a Word document without metadata."""
    docx_path = FIXTURE_DIR / 'no_metadata.docx'
    
    with zipfile.ZipFile(docx_path, 'w') as zf:
        content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''
        zf.writestr('[Content_Types].xml', content_types)
        
        rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
        zf.writestr('_rels/.rels', rels)
        
        document = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r>
        <w:t>This document has no title or author metadata.</w:t>
      </w:r>
    </w:p>
  </w:body>
</w:document>'''
        zf.writestr('word/document.xml', document)
    
    print(f"Created: {docx_path}")


def create_with_header_footer_docx():
    """Create a Word document with headers and footers."""
    docx_path = FIXTURE_DIR / 'with_header_footer.docx'
    
    with zipfile.ZipFile(docx_path, 'w') as zf:
        content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
</Types>'''
        zf.writestr('[Content_Types].xml', content_types)
        
        rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
        zf.writestr('_rels/.rels', rels)
        
        document = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r>
        <w:t>Main document content goes here.</w:t>
      </w:r>
    </w:p>
  </w:body>
</w:document>'''
        zf.writestr('word/document.xml', document)
        
        header = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p>
    <w:r>
      <w:t>CONFIDENTIAL HEADER</w:t>
    </w:r>
  </w:p>
</w:hdr>'''
        zf.writestr('word/header1.xml', header)
        
        footer = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p>
    <w:r>
      <w:t>Page Footer - Company Name</w:t>
    </w:r>
  </w:p>
</w:ftr>'''
        zf.writestr('word/footer1.xml', footer)
    
    print(f"Created: {docx_path}")


def create_with_tabs_breaks_docx():
    """Create a Word document with tabs and line breaks."""
    docx_path = FIXTURE_DIR / 'with_tabs_breaks.docx'
    
    with zipfile.ZipFile(docx_path, 'w') as zf:
        content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''
        zf.writestr('[Content_Types].xml', content_types)
        
        rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
        zf.writestr('_rels/.rels', rels)
        
        document = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r>
        <w:t>Column1</w:t>
      </w:r>
      <w:r>
        <w:tab/>
      </w:r>
      <w:r>
        <w:t>Column2</w:t>
      </w:r>
      <w:r>
        <w:tab/>
      </w:r>
      <w:r>
        <w:t>Column3</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:r>
        <w:t>Line one</w:t>
      </w:r>
      <w:r>
        <w:br/>
      </w:r>
      <w:r>
        <w:t>Line two after break</w:t>
      </w:r>
    </w:p>
  </w:body>
</w:document>'''
        zf.writestr('word/document.xml', document)
    
    print(f"Created: {docx_path}")


if __name__ == '__main__':
    create_sample_docx()
    create_no_metadata_docx()
    create_with_header_footer_docx()
    create_with_tabs_breaks_docx()
    print("Done!")
