"""
CLI package for doc-search.

This package provides the command-line interface for crawling
and searching documentation sites.
"""

from .parsers import create_parser


def main():
    """Main entry point for the CLI."""
    import sys
    
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


__all__ = ['main']
