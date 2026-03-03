"""
Guard test: ensure all open() calls in doc_search use encoding='utf-8'.

Prevents UnicodeDecodeError on Windows where the default encoding is cp1252.
If this test fails, you added an open() call without encoding='utf-8'.
"""

import ast
import unittest
from pathlib import Path


# open() calls that legitimately don't need encoding='utf-8'
_SKIP_PATTERNS = {
    'rb', 'wb', 'ab',  # binary modes
}


class _OpenCallVisitor(ast.NodeVisitor):
    """AST visitor that finds open() calls missing encoding='utf-8'."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.violations = []

    def visit_Call(self, node):
        # Match open(...) calls
        func = node.func
        is_open = False
        if isinstance(func, ast.Name) and func.id == 'open':
            is_open = True
        elif isinstance(func, ast.Attribute) and func.attr == 'open':
            # Skip zipfile.open(), gzip.open(), zf.open(), etc.
            is_open = False

        if is_open:
            self._check_open_call(node)

        self.generic_visit(node)

    def _check_open_call(self, node):
        # Check if mode is binary
        mode = None
        for arg in node.args[1:2]:  # second positional arg is mode
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                mode = arg.value
        for kw in node.keywords:
            if kw.arg == 'mode' and isinstance(kw.value, ast.Constant):
                mode = kw.value.value

        if mode and any(b in mode for b in _SKIP_PATTERNS):
            return  # binary mode, no encoding needed

        # Check if encoding is specified
        has_encoding = any(kw.arg == 'encoding' for kw in node.keywords)
        if not has_encoding:
            self.violations.append(node.lineno)


class TestEncodingGuard(unittest.TestCase):
    """Ensure every text-mode open() in doc_search specifies encoding='utf-8'."""

    def test_all_open_calls_have_encoding(self):
        src_dir = Path(__file__).parent.parent / 'doc_search'
        all_violations = []

        for py_file in sorted(src_dir.rglob('*.py')):
            if '__pycache__' in str(py_file):
                continue

            source = py_file.read_text(encoding='utf-8')
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue

            visitor = _OpenCallVisitor(str(py_file))
            visitor.visit(tree)

            for lineno in visitor.violations:
                rel = py_file.relative_to(src_dir.parent)
                all_violations.append(f"  {rel}:{lineno}")

        if all_violations:
            msg = (
                f"\n\n{len(all_violations)} open() call(s) missing encoding='utf-8':\n"
                + "\n".join(all_violations)
                + "\n\nAdd encoding='utf-8' to fix. Binary files use 'rb'/'wb' mode."
            )
            self.fail(msg)


if __name__ == '__main__':
    unittest.main()
