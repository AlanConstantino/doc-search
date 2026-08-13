"""Foundation layer: constants, config, URLs, HTTP, tokenization.

Nothing in ``core`` may import crawl, extract, index, search, or app.
"""

from .constants import *  # noqa: F401,F403
from .config import (
    apply_runtime_config,
    expand_path,
    find_config_file,
    get_default_sites_dir,
    get_loaded_config_path,
    get_sites_dir,
    load_config,
    reload_config,
    reset_config_cache,
    set_explicit_config_path,
    write_example_config,
)
from .http import create_permissive_ssl_context, make_basic_auth_header
from .stemmer import stem
from .text import (
    STOP_WORDS,
    format_duration,
    format_size,
    tokenize,
    tokenize_phrase,
    tokenize_with_exact,
)
from .urls import (
    get_domain,
    hash_string,
    is_html_content,
    is_same_domain,
    is_valid_url,
    normalize_url,
    resolve_url,
    sanitize_url,
    site_hash,
    url_to_filename,
)

__all__ = [
    'STOP_WORDS',
    'apply_runtime_config',
    'create_permissive_ssl_context',
    'expand_path',
    'find_config_file',
    'format_duration',
    'format_size',
    'get_default_sites_dir',
    'get_domain',
    'get_loaded_config_path',
    'get_sites_dir',
    'hash_string',
    'is_html_content',
    'is_same_domain',
    'is_valid_url',
    'load_config',
    'make_basic_auth_header',
    'normalize_url',
    'reload_config',
    'reset_config_cache',
    'resolve_url',
    'sanitize_url',
    'set_explicit_config_path',
    'site_hash',
    'stem',
    'tokenize',
    'tokenize_phrase',
    'tokenize_with_exact',
    'url_to_filename',
    'write_example_config',
]
