"""
CLI package for doc-search.

Command-line interface for crawling and searching documentation sites.
"""

from .parsers import create_parser


def main(argv=None):
    """Main entry point for the CLI.

    Always loads the top-level JSON config (and env overrides) before
    dispatching a command so ``sites_dir`` is active by default.
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    from ...core.config import apply_runtime_config, get_loaded_config_path
    from . import commands as commands_mod

    config_path = getattr(args, 'config', None)
    sites_dir = apply_runtime_config(config_path=config_path)
    commands_mod.DEFAULT_DATA_DIR = sites_dir

    if not args.command:
        parser.print_help()
        cfg = get_loaded_config_path()
        print()
        print(f"Sites directory: {sites_dir}")
        if cfg:
            print(f"Config: {cfg}")
        return 1

    return args.func(args)


__all__ = ['main', 'create_parser']
