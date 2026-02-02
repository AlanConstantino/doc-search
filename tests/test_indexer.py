"""Tests for BM25Index class."""

import unittest
from doc_search.indexer import BM25Index


class TestBM25IndexParameters(unittest.TestCase):
    """Tests for BM25 parameter validation."""
    
    def test_default_parameters(self):
        """Default parameters should work."""
        index = BM25Index()
        self.assertEqual(index.k1, 1.5)
        self.assertEqual(index.b, 0.75)
        self.assertTrue(index.stem)
    
    def test_custom_valid_parameters(self):
        """Custom valid parameters should work."""
        index = BM25Index(k1=2.0, b=0.5, stem=False)
        self.assertEqual(index.k1, 2.0)
        self.assertEqual(index.b, 0.5)
        self.assertFalse(index.stem)
    
    def test_k1_zero_allowed(self):
        """k1=0 should be allowed."""
        index = BM25Index(k1=0)
        self.assertEqual(index.k1, 0)
    
    def test_k1_negative_rejected(self):
        """Negative k1 should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            BM25Index(k1=-0.5)
        self.assertIn('k1', str(ctx.exception))
    
    def test_b_zero_allowed(self):
        """b=0 should be allowed (no length normalization)."""
        index = BM25Index(b=0)
        self.assertEqual(index.b, 0)
    
    def test_b_one_allowed(self):
        """b=1 should be allowed (full length normalization)."""
        index = BM25Index(b=1)
        self.assertEqual(index.b, 1)
    
    def test_b_negative_rejected(self):
        """Negative b should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            BM25Index(b=-0.1)
        self.assertIn('b', str(ctx.exception))
    
    def test_b_greater_than_one_rejected(self):
        """b > 1 should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            BM25Index(b=1.5)
        self.assertIn('b', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
