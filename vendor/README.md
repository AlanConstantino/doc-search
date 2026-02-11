# Vendored Dependencies

This directory contains vendored (bundled) third-party libraries to avoid requiring users to install dependencies via pip.

## openpyxl v3.1.2

- **Source:** https://github.com/theorchard/openpyxl
- **License:** MIT
- **Vendored:** 2026-02-11
- **Purpose:** Excel (.xlsx) text extraction
- **Python:** 3.6+ required

### License Notice

openpyxl is licensed under the MIT license.

Copyright (c) 2010 openpyxl

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

### Usage

```python
from vendor.openpyxl import load_workbook

wb = load_workbook("spreadsheet.xlsx")
for sheet_name in wb.sheetnames:
    sheet = wb[sheet_name]
    for row in sheet.iter_rows(values_only=True):
        print(row)
```

---

## et_xmlfile v2.0.0

- **Source:** https://pypi.org/project/et-xmlfile/
- **License:** MIT
- **Vendored:** 2026-02-11
- **Purpose:** Required dependency of openpyxl for XML handling

---

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
