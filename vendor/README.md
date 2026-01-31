# Vendored Dependencies

This directory contains vendored (bundled) third-party libraries to avoid requiring users to install dependencies via pip.

## pypdf v6.6.2

- **Source:** https://github.com/py-pdf/pypdf
- **License:** BSD-3-Clause
- **Vendored:** 2026-01-31
- **Purpose:** PDF text extraction for document indexing

### License Notice

pypdf is licensed under the BSD-3-Clause license. See the original repository for full license text.

### Usage

```python
from vendor.pypdf import PdfReader

reader = PdfReader("document.pdf")
for page in reader.pages:
    text = page.extract_text()
```

### Notes

- Pure Python, no C extensions required
- Optional dependencies (cryptography, Pillow) are NOT included
- Encrypted PDFs will not be readable without installing cryptography separately
- Image extraction requires Pillow (not vendored)
