# Vendored Dependencies

This directory contains vendored (bundled) third-party libraries to avoid requiring users to install dependencies via pip.

## PyPDF2 v3.0.1

- **Source:** https://github.com/py-pdf/PyPDF2
- **License:** BSD-3-Clause
- **Vendored:** 2026-01-31
- **Purpose:** PDF text extraction for document indexing
- **Python:** 3.6+ compatible

### License Notice

PyPDF2 is licensed under the BSD-3-Clause license. See the original repository for full license text.

### Why PyPDF2 instead of pypdf?

PyPDF2 v3.0.x is the last version before the library was renamed to `pypdf`. The newer `pypdf` requires Python 3.9+, while PyPDF2 supports Python 3.6+, allowing doc-search to run on older Python installations.

### Usage

```python
from vendor.PyPDF2 import PdfReader

reader = PdfReader("document.pdf")
for page in reader.pages:
    text = page.extract_text()
```

### Notes

- Pure Python, no C extensions required
- Optional dependencies (cryptography, Pillow) are NOT included
- Encrypted PDFs will not be readable without installing cryptography separately
- Image extraction requires Pillow (not vendored)
- Deprecation warning is suppressed in pdf_extractor.py (library is unmaintained but stable)
