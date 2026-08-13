"""Filesystem anchors for the installed/source package."""

from pathlib import Path

# doc_search/  (the Python package)
PACKAGE_ROOT = Path(__file__).resolve().parent.parent

# Repository / project root when running from a checkout.
# When installed as a package this is the parent of the package dir.
REPO_ROOT = PACKAGE_ROOT.parent

VENDOR_DIR = REPO_ROOT / "vendor"
DATA_DIR = Path(__file__).resolve().parent / "data"
