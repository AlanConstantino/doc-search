# Vendored Dependencies

This directory contains vendored (bundled) third-party libraries to avoid requiring users to install dependencies via pip.

## pypdf v6.7.0

- **Source:** https://github.com/py-pdf/pypdf
- **License:** BSD-3-Clause
- **Vendored:** 2025-02-11
- **Purpose:** PDF text extraction with font-aware heading detection
- **Python:** 3.9+ required

### License Notice

pypdf is licensed under the BSD-3-Clause license. See the original repository for full license text.

Copyright (c) 2006-2008, Mathieu Fenniak
Copyright (c) 2022-present, py-pdf contributors

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.

### Why pypdf?

pypdf (formerly PyPDF2) is the actively maintained continuation of the original project. Key benefits:

- **Visitor pattern** for text extraction gives access to font sizes and font names
- **Heading detection** via font size analysis
- **Active development** with regular updates
- **Better text extraction** with layout preservation options

### Usage

```python
from vendor.pypdf import PdfReader

reader = PdfReader("document.pdf")
for page in reader.pages:
    text = page.extract_text()

# With visitor pattern for font-aware extraction
def visitor(text, cm, tm, font_dict, font_size):
    print(f"Text: {text}, Font size: {font_size}")

page.extract_text(visitor_text=visitor)
```

### Notes

- Pure Python, no C extensions required
- Optional dependencies (cryptography, Pillow) are NOT included
- Encrypted PDFs will not be readable without installing cryptography separately
- Image extraction requires Pillow (not vendored)
