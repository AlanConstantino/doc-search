"""
Pytest configuration and shared fixtures.
"""

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "benchmark: mark test as a performance benchmark (deselect with '-m \"not benchmark\"')"
    )
