"""
Application configuration for doc-search.

Loads a top-level JSON config that can override where crawled site data
is stored (the "sites" directory).

The CLI loads this automatically on every run (see ``apply_runtime_config``).

Lookup order for the config file (first existing file wins):
  1. Path from ``--config`` / ``apply_runtime_config(config_path=...)``
  2. Path in DOC_SEARCH_CONFIG environment variable
  3. ./doc_search.json  (current working directory)
  4. <package-parent>/doc_search.json  (project/repo root next to the package)
  5. <home>/.doc_search/config.json  (user-global)

sites_dir resolution order:
  1. DOC_SEARCH_SITES_DIR environment variable
  2. "sites_dir" key in the loaded config file
  3. Built-in default: <home>/.doc_search/sites

Example doc_search.json / config.json (portable — works on Windows, macOS, Linux)::

    {
      "sites_dir": "~/.doc_search/sites"
    }

Path strings are expanded cross-platform:
  - ``~`` / ``~/...`` → user home (Path.home / expanduser)
  - ``$VAR`` / ``${VAR}`` → environment variables (POSIX-style)
  - ``%VAR%`` → environment variables (Windows-style)
  - ``/`` and ``\\`` separators both accepted (normalized via pathlib)
  - Relative paths resolve against the current working directory
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

_PROJECT_CONFIG_NAME = 'doc_search.json'
_APP_DIR_NAME = '.doc_search'
_SITES_DIR_NAME = 'sites'
_USER_CONFIG_NAME = 'config.json'

# Package directory (doc_search/) and its parent (repo/project root when
# running from a source checkout; may not contain a config when installed).
_PACKAGE_DIR = Path(__file__).resolve().parent
_PACKAGE_PARENT_DIR = _PACKAGE_DIR.parent

# Explicit override set by CLI --config / apply_runtime_config(config_path=...)
_explicit_config_path: Optional[Path] = None

# Module-level cache (cleared via reload_config / reset in tests)
_cached_config: Optional[Dict[str, Any]] = None
_cached_config_path: Optional[Path] = None

# Matches $VAR or ${VAR} (POSIX env references)
_ENV_VAR_PATTERN = re.compile(
    r'\$([A-Za-z_][A-Za-z0-9_]*)|\$\{([A-Za-z_][A-Za-z0-9_]*)\}'
)
# Matches %VAR% (Windows env references)
_WIN_ENV_PATTERN = re.compile(r'%([A-Za-z_][A-Za-z0-9_]*)%')


def get_home_dir() -> Path:
    """Return the current user home directory (live lookup)."""
    return Path.home()


def get_default_sites_dir() -> Path:
    """Return the built-in default sites directory (no env/file overrides)."""
    return get_home_dir() / _APP_DIR_NAME / _SITES_DIR_NAME


def get_user_config_path() -> Path:
    """Return the user-global config path (<home>/.doc_search/config.json)."""
    return get_home_dir() / _APP_DIR_NAME / _USER_CONFIG_NAME


def get_package_config_path() -> Path:
    """Return <package-parent>/doc_search.json (project root next to the package)."""
    return _PACKAGE_PARENT_DIR / _PROJECT_CONFIG_NAME


def set_explicit_config_path(path: Optional[Union[str, Path]]) -> None:
    """
    Set or clear an explicit config file path (e.g. from ``--config``).

    Clears the load cache so the next lookup picks up the new path.
    """
    global _explicit_config_path
    if path is None or str(path).strip() == '':
        _explicit_config_path = None
    else:
        _explicit_config_path = expand_path(path)
    reset_config_cache()


def get_explicit_config_path() -> Optional[Path]:
    """Return the explicit config path set via CLI/API, if any."""
    return _explicit_config_path


def iter_config_paths() -> List[Path]:
    """
    Ordered list of candidate config file paths.

    Deduplicates while preserving priority order.
    """
    paths: List[Path] = []
    seen = set()

    def _add(p: Path) -> None:
        try:
            key = str(p.resolve()) if p.exists() else str(p)
        except OSError:
            key = str(p)
        if key in seen:
            return
        seen.add(key)
        paths.append(p)

    if _explicit_config_path is not None:
        _add(_explicit_config_path)

    env_path = os.environ.get('DOC_SEARCH_CONFIG', '').strip()
    if env_path:
        _add(expand_path(env_path))

    _add(Path.cwd() / _PROJECT_CONFIG_NAME)
    _add(get_package_config_path())
    _add(get_user_config_path())
    return paths


def find_config_file() -> Optional[Path]:
    """Return the first existing config file path, or None."""
    for path in iter_config_paths():
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def load_config(force_reload: bool = False) -> Dict[str, Any]:
    """
    Load configuration from the first available JSON config file.

    Returns an empty dict when no file is found or the file is invalid.
    When an explicit ``--config`` path is set but missing/invalid, returns
    empty dict (caller may warn); other candidates are still tried only if
    no explicit path was set.
    """
    global _cached_config, _cached_config_path

    if _cached_config is not None and not force_reload:
        return _cached_config

    config: Dict[str, Any] = {}
    chosen: Optional[Path] = None

    candidates = iter_config_paths()
    # If user forced a path, only load that file (don't silently fall through).
    if _explicit_config_path is not None:
        candidates = [_explicit_config_path]

    for path in candidates:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue

        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue

        if isinstance(data, dict):
            config = data
            chosen = path
            break

    _cached_config = config
    _cached_config_path = chosen
    return config


def get_loaded_config_path() -> Optional[Path]:
    """Path of the config file last loaded by load_config(), if any."""
    load_config()
    return _cached_config_path


def reload_config() -> Dict[str, Any]:
    """Clear the cache and reload configuration from disk."""
    return load_config(force_reload=True)


def reset_config_cache() -> None:
    """Drop cached config (for tests)."""
    global _cached_config, _cached_config_path
    _cached_config = None
    _cached_config_path = None


def _expand_env_vars(value: str) -> str:
    """
    Expand $VAR, ${VAR}, and %VAR% references in a path string.

    Unknown variables are left unchanged so partial paths remain visible.
    Uses os.environ only (not os.path.expandvars) so behavior is consistent
    across platforms and both POSIX and Windows spellings work everywhere.
    """
    def _posix_repl(match: re.Match) -> str:
        name = match.group(1) or match.group(2)
        return os.environ.get(name, match.group(0))

    def _win_repl(match: re.Match) -> str:
        name = match.group(1)
        return os.environ.get(name, match.group(0))

    value = _ENV_VAR_PATTERN.sub(_posix_repl, value)
    value = _WIN_ENV_PATTERN.sub(_win_repl, value)
    return value


def _normalize_separators(value: str) -> str:
    """
    Convert backslashes to forward slashes for pathlib.

    pathlib on POSIX treats ``\\`` as a normal character, not a separator.
    Windows pathlib accepts ``/``. Normalizing lets one config string work
    on Windows, macOS, and Linux.
    """
    return value.replace('\\', '/')


def expand_path(value: Union[str, Path]) -> Path:
    """
    Expand a user path string into an absolute ``Path`` on any OS.

    Handles:
      * ``Path`` instances (returned resolved)
      * ``~`` and ``~/...`` via expanduser
      * ``$HOME``, ``${HOME}``, ``%USERPROFILE%``, etc.
      * Mixed ``/`` and ``\\`` separators
      * Relative paths (resolved against cwd)
    """
    if isinstance(value, Path):
        try:
            return value.expanduser().resolve()
        except OSError:
            return value.expanduser().absolute()

    text = str(value).strip()
    if not text:
        return Path.cwd().resolve()

    # Env vars first so e.g. "$HOME/.doc_search" or "%USERPROFILE%\\.doc_search" work
    text = _expand_env_vars(text)

    # Strip wrapping quotes people sometimes paste into JSON-adjacent configs
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        text = text[1:-1]

    # pathlib on POSIX does not treat backslash as a separator — normalize.
    text = _normalize_separators(text)

    path = Path(text).expanduser()

    # resolve() absolute-izes and normalizes .. / . without requiring the path
    # to exist (important before first crawl).
    try:
        return path.resolve()
    except OSError:
        # Extremely broken paths (e.g. invalid Windows device names): best-effort
        return path.absolute()


# Older private name kept as alias
_expand_dir = expand_path


def get_sites_dir(config: Optional[Dict[str, Any]] = None) -> Path:
    """
    Resolve the sites data directory.

    Order:
      1. DOC_SEARCH_SITES_DIR env var
      2. config["sites_dir"] (loaded file or provided dict)
      3. <home>/.doc_search/sites
    """
    env_dir = os.environ.get('DOC_SEARCH_SITES_DIR', '').strip()
    if env_dir:
        return expand_path(env_dir)

    if config is None:
        config = load_config()

    sites_dir = config.get('sites_dir')
    if sites_dir is not None and str(sites_dir).strip():
        return expand_path(str(sites_dir))

    return get_default_sites_dir()


def apply_runtime_config(
    config_path: Optional[Union[str, Path]] = None,
    *,
    reload: bool = True,
) -> Path:
    """
    Apply config for a tool run and return the resolved sites directory.

    Called automatically by the CLI on every invocation so ``doc_search.json``
    (or env overrides) is always in effect — not only at import time.

    Args:
        config_path: Optional explicit config file (from ``--config``).
            Pass ``None`` (default) to clear any previous explicit path and
            use the normal lookup order.
        reload: When True (default), clear cache and re-read from disk.

    Returns:
        Resolved sites data directory path.
    """
    # Always bind/clear explicit path for this run so a prior --config cannot stick.
    set_explicit_config_path(config_path)

    if reload:
        load_config(force_reload=True)
    else:
        load_config()

    return get_sites_dir()


def default_config_dict() -> Dict[str, Any]:
    """
    Return a dict suitable for writing a starter config file.

    Uses the portable ``~/...`` form so the same file works on
    Windows, macOS, and Linux after expanduser.
    """
    return {
        'sites_dir': '~/{}/{}'.format(_APP_DIR_NAME, _SITES_DIR_NAME),
    }


def write_example_config(
    path: Path,
    sites_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Write a starter config JSON to ``path``.

    Args:
        path: Destination file path
        sites_dir: Optional override for the sites_dir value

    Returns:
        The path written
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = default_config_dict()
    if sites_dir is not None:
        # Keep user-provided string as-is when given a str (portable tokens);
        # stringify Path with as_posix() so committed examples stay readable.
        if isinstance(sites_dir, Path):
            data['sites_dir'] = sites_dir.as_posix()
        else:
            data['sites_dir'] = str(sites_dir)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    return path


def __getattr__(name: str):
    """Live back-compat for ``_DEFAULT_SITES_DIR`` / ``_USER_CONFIG_PATH``."""
    if name == '_DEFAULT_SITES_DIR':
        return get_default_sites_dir()
    if name == '_USER_CONFIG_PATH':
        return get_user_config_path()
    raise AttributeError('module {!r} has no attribute {!r}'.format(__name__, name))
