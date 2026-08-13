"""Tests for doc_search.config — portable sites_dir + CLI default loading."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from doc_search import config as cfg
from doc_search.cli import commands
from doc_search.cli import main as cli_main


@pytest.fixture(autouse=True)
def _clean_config_env(monkeypatch, tmp_path):
    """Isolate config lookup from the real repo / user home."""
    monkeypatch.delenv('DOC_SEARCH_CONFIG', raising=False)
    monkeypatch.delenv('DOC_SEARCH_SITES_DIR', raising=False)
    # Avoid picking up the repo's doc_search.json via cwd
    monkeypatch.chdir(tmp_path)
    # Point home away from the real user for Path.home() / expanduser
    fake_home = tmp_path / 'home'
    fake_home.mkdir()
    monkeypatch.setattr(Path, 'home', staticmethod(lambda: fake_home))
    # expanduser reads HOME (POSIX) or USERPROFILE (Windows)
    monkeypatch.setenv('HOME', str(fake_home))
    monkeypatch.setenv('USERPROFILE', str(fake_home))
    if sys.platform == 'win32':
        monkeypatch.setenv('HOMEDRIVE', str(fake_home.drive) if fake_home.drive else 'C:')
        monkeypatch.setenv('HOMEPATH', str(fake_home)[2:] if len(str(fake_home)) > 2 else '\\')
    # Don't let the real package-root doc_search.json leak into unit tests
    # unless a test explicitly opts in via the real path.
    monkeypatch.setattr(cfg, '_PACKAGE_PARENT_DIR', tmp_path / 'no-package-config')
    cfg.set_explicit_config_path(None)
    cfg.reset_config_cache()
    yield
    cfg.set_explicit_config_path(None)
    cfg.reset_config_cache()
    try:
        commands.DEFAULT_DATA_DIR = cfg.get_sites_dir()
    except Exception:
        pass


def test_default_sites_dir_is_under_home():
    expected = Path.home() / '.doc_search' / 'sites'
    assert cfg.get_sites_dir() == expected
    assert cfg.get_default_sites_dir() == expected


def test_project_doc_search_json_sets_sites_dir(tmp_path):
    custom = tmp_path / 'my-sites'
    (tmp_path / 'doc_search.json').write_text(
        json.dumps({'sites_dir': str(custom)}), encoding='utf-8'
    )
    cfg.reset_config_cache()
    assert cfg.get_sites_dir() == custom.resolve()
    loaded = cfg.get_loaded_config_path()
    assert loaded is not None
    assert loaded.name == 'doc_search.json'


def test_user_config_json_sets_sites_dir(tmp_path):
    user_cfg = cfg.get_user_config_path()
    user_cfg.parent.mkdir(parents=True, exist_ok=True)
    custom = tmp_path / 'user-sites'
    user_cfg.write_text(json.dumps({'sites_dir': str(custom)}), encoding='utf-8')
    cfg.reset_config_cache()
    assert cfg.get_sites_dir() == custom.resolve()


def test_package_root_config_used_when_no_cwd_config(tmp_path, monkeypatch):
    """Running outside the repo still picks up package-adjacent doc_search.json."""
    package_root = tmp_path / 'pkg_root'
    package_root.mkdir()
    custom = tmp_path / 'package-sites'
    (package_root / 'doc_search.json').write_text(
        json.dumps({'sites_dir': str(custom)}), encoding='utf-8'
    )
    monkeypatch.setattr(cfg, '_PACKAGE_PARENT_DIR', package_root)
    # cwd has no config
    cfg.reset_config_cache()
    assert cfg.get_sites_dir() == custom.resolve()
    assert cfg.get_loaded_config_path() == (package_root / 'doc_search.json').resolve()


def test_cwd_config_wins_over_package_root(tmp_path, monkeypatch):
    package_root = tmp_path / 'pkg_root'
    package_root.mkdir()
    pkg_sites = tmp_path / 'pkg-sites'
    cwd_sites = tmp_path / 'cwd-sites'
    (package_root / 'doc_search.json').write_text(
        json.dumps({'sites_dir': str(pkg_sites)}), encoding='utf-8'
    )
    (tmp_path / 'doc_search.json').write_text(
        json.dumps({'sites_dir': str(cwd_sites)}), encoding='utf-8'
    )
    monkeypatch.setattr(cfg, '_PACKAGE_PARENT_DIR', package_root)
    cfg.reset_config_cache()
    assert cfg.get_sites_dir() == cwd_sites.resolve()


def test_env_config_path_wins_over_project(tmp_path, monkeypatch):
    project_dir = tmp_path / 'proj-sites'
    env_dir = tmp_path / 'env-sites'
    (tmp_path / 'doc_search.json').write_text(
        json.dumps({'sites_dir': str(project_dir)}), encoding='utf-8'
    )
    env_cfg = tmp_path / 'custom-config.json'
    env_cfg.write_text(json.dumps({'sites_dir': str(env_dir)}), encoding='utf-8')
    monkeypatch.setenv('DOC_SEARCH_CONFIG', str(env_cfg))
    cfg.reset_config_cache()
    assert cfg.get_sites_dir() == env_dir.resolve()


def test_sites_dir_env_wins_over_config_file(tmp_path, monkeypatch):
    file_dir = tmp_path / 'from-file'
    env_dir = tmp_path / 'from-env'
    (tmp_path / 'doc_search.json').write_text(
        json.dumps({'sites_dir': str(file_dir)}), encoding='utf-8'
    )
    monkeypatch.setenv('DOC_SEARCH_SITES_DIR', str(env_dir))
    cfg.reset_config_cache()
    assert cfg.get_sites_dir() == env_dir.resolve()


def test_tilde_expansion(tmp_path):
    (tmp_path / 'doc_search.json').write_text(
        json.dumps({'sites_dir': '~/.doc_search/sites'}), encoding='utf-8'
    )
    cfg.reset_config_cache()
    assert cfg.get_sites_dir() == (Path.home() / '.doc_search' / 'sites').resolve()


def test_tilde_only():
    assert cfg.expand_path('~') == Path.home().resolve()


def test_posix_env_var_expansion(tmp_path, monkeypatch):
    target = tmp_path / 'from-home-env'
    monkeypatch.setenv('MY_DOC_ROOT', str(tmp_path))
    assert cfg.expand_path('$MY_DOC_ROOT/from-home-env') == target.resolve()
    assert cfg.expand_path('${MY_DOC_ROOT}/from-home-env') == target.resolve()


def test_windows_env_var_expansion(tmp_path, monkeypatch):
    """%VAR% works on every OS so one config form is portable."""
    target = tmp_path / 'win-style'
    monkeypatch.setenv('MY_DOC_ROOT', str(tmp_path))
    assert cfg.expand_path('%MY_DOC_ROOT%/win-style') == target.resolve()


def test_mixed_separators(tmp_path):
    """Forward slashes in config work even when the OS prefers backslash."""
    custom = tmp_path / 'a' / 'b'
    custom.mkdir(parents=True)
    slash_path = str(tmp_path).replace('\\', '/') + '/a/b'
    assert cfg.expand_path(slash_path) == custom.resolve()


def test_backslash_separators(tmp_path):
    """Backslash separators are accepted (native Windows paths)."""
    custom = tmp_path / 'x' / 'y'
    bs_path = str(tmp_path) + '\\x\\y'
    assert cfg.expand_path(bs_path) == custom.resolve()


def test_relative_path_resolves_against_cwd(tmp_path):
    rel = Path('relative-sites')
    assert cfg.expand_path('relative-sites') == (tmp_path / rel).resolve()


def test_quoted_path_stripped(tmp_path):
    custom = tmp_path / 'quoted'
    assert cfg.expand_path(f'"{custom}"') == custom.resolve()
    assert cfg.expand_path(f"'{custom}'") == custom.resolve()


def test_portable_default_config_dict_uses_tilde():
    data = cfg.default_config_dict()
    assert data['sites_dir'] == '~/.doc_search/sites'
    assert cfg.expand_path(data['sites_dir']) == (
        Path.home() / '.doc_search' / 'sites'
    ).resolve()


def test_invalid_json_falls_back_to_default(tmp_path):
    (tmp_path / 'doc_search.json').write_text('{not-json', encoding='utf-8')
    cfg.reset_config_cache()
    assert cfg.get_sites_dir() == (Path.home() / '.doc_search' / 'sites')


def test_write_example_config(tmp_path):
    path = tmp_path / 'out' / 'doc_search.json'
    written = cfg.write_example_config(path, sites_dir='~/data/sites')
    assert written == path
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['sites_dir'] == '~/data/sites'
    raw = path.read_bytes()
    assert b'\r\n' not in raw


def test_commands_default_data_dir_uses_config(tmp_path):
    custom = tmp_path / 'cli-sites'
    (tmp_path / 'doc_search.json').write_text(
        json.dumps({'sites_dir': str(custom)}), encoding='utf-8'
    )
    commands.refresh_default_data_dir()
    assert commands.DEFAULT_DATA_DIR == custom.resolve()
    site = commands.get_site_dir('https://docs.example.com/guide')
    assert site.parent == custom.resolve()


def test_reload_config_picks_up_changes(tmp_path):
    first = tmp_path / 'a'
    second = tmp_path / 'b'
    cfg_path = tmp_path / 'doc_search.json'
    cfg_path.write_text(json.dumps({'sites_dir': str(first)}), encoding='utf-8')
    assert cfg.get_sites_dir() == first.resolve()
    cfg_path.write_text(json.dumps({'sites_dir': str(second)}), encoding='utf-8')
    assert cfg.get_sites_dir() == first.resolve()  # cached
    cfg.reload_config()
    assert cfg.get_sites_dir() == second.resolve()


def test_compat_module_attrs_track_live_home():
    """_DEFAULT_SITES_DIR / _USER_CONFIG_PATH are live, not import-frozen."""
    assert cfg._DEFAULT_SITES_DIR == Path.home() / '.doc_search' / 'sites'
    assert cfg._USER_CONFIG_PATH == Path.home() / '.doc_search' / 'config.json'


def test_empty_sites_dir_value_falls_back(tmp_path):
    (tmp_path / 'doc_search.json').write_text(
        json.dumps({'sites_dir': '   '}), encoding='utf-8'
    )
    cfg.reset_config_cache()
    assert cfg.get_sites_dir() == Path.home() / '.doc_search' / 'sites'


def test_userprofile_style_default_on_any_os(tmp_path, monkeypatch):
    """A Windows-flavored config expands via %USERPROFILE% everywhere."""
    (tmp_path / 'doc_search.json').write_text(
        json.dumps({'sites_dir': r'%USERPROFILE%\.doc_search\sites'}),
        encoding='utf-8',
    )
    cfg.reset_config_cache()
    assert cfg.get_sites_dir() == (Path.home() / '.doc_search' / 'sites').resolve()


def test_apply_runtime_config_reloads_each_call(tmp_path):
    first = tmp_path / 'a'
    second = tmp_path / 'b'
    cfg_path = tmp_path / 'doc_search.json'
    cfg_path.write_text(json.dumps({'sites_dir': str(first)}), encoding='utf-8')
    assert cfg.apply_runtime_config() == first.resolve()
    cfg_path.write_text(json.dumps({'sites_dir': str(second)}), encoding='utf-8')
    # Without apply/reload, cache would stick; apply_runtime_config reloads
    assert cfg.apply_runtime_config() == second.resolve()


def test_cli_main_loads_config_by_default(tmp_path, capsys):
    """python -m doc_search list uses doc_search.json without extra flags."""
    custom = tmp_path / 'cli-default-sites'
    custom.mkdir()
    (tmp_path / 'doc_search.json').write_text(
        json.dumps({'sites_dir': str(custom)}), encoding='utf-8'
    )
    # Pretend no sites yet
    rc = cli_main(['list'])
    assert rc == 0
    out = capsys.readouterr().out
    assert str(custom.resolve()) in out
    assert 'doc_search.json' in out
    assert commands.DEFAULT_DATA_DIR == custom.resolve()


def test_cli_main_config_flag(tmp_path, capsys):
    """--config PATH forces a specific config file."""
    other = tmp_path / 'other.json'
    custom = tmp_path / 'flag-sites'
    custom.mkdir()
    other.write_text(json.dumps({'sites_dir': str(custom)}), encoding='utf-8')
    # cwd config points elsewhere — should be ignored when --config is set
    (tmp_path / 'doc_search.json').write_text(
        json.dumps({'sites_dir': str(tmp_path / 'ignored')}), encoding='utf-8'
    )
    rc = cli_main(['--config', str(other), 'list'])
    assert rc == 0
    out = capsys.readouterr().out
    assert str(custom.resolve()) in out
    assert 'other.json' in out


def test_cli_main_help_shows_sites_dir(tmp_path, capsys):
    """Bare invocation still reports which config/sites dir would be used."""
    custom = tmp_path / 'help-sites'
    (tmp_path / 'doc_search.json').write_text(
        json.dumps({'sites_dir': str(custom)}), encoding='utf-8'
    )
    rc = cli_main([])
    assert rc == 1
    out = capsys.readouterr().out
    assert 'Sites directory:' in out
    assert str(custom.resolve()) in out
