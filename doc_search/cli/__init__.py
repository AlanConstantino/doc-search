"""
CLI package for doc-search.

This package provides the command-line interface for crawling
and searching documentation sites.
"""

from .parsers import create_parser


def main(argv=None):
    """Main entry point for the CLI.

    Always loads the top-level JSON config (and env overrides) before
    dispatching a command so ``sites_dir`` is active by default.
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # Apply config before any command runs. DEFAULT_DATA_DIR is refreshed
    # so crawl/index/search/list all see the configured sites path.
    from ..config import apply_runtime_config, get_loaded_config_path
    from . import commands as commands_mod

    config_path = getattr(args, 'config', None)
    sites_dir = apply_runtime_config(config_path=config_path)
    commands_mod.DEFAULT_DATA_DIR = sites_dir

    # Keep multi_search in sync when it imported DEFAULT_DATA_DIR earlier.
    try:
        from .. import multi_search as multi_search_mod
        multi_search_mod.DEFAULT_DATA_DIR = sites_dir
    except Exception:
        pass

    if not args.command:
        parser.print_help()
        # Still show which config would be used (helps first-run setup)
        cfg = get_loaded_config_path()
        print()
        print(f"Sites directory: {sites_dir}")
        if cfg:
            print(f"Config: {cfg}")
        return 1

    return args.func(args)


__all__ = ['main']
