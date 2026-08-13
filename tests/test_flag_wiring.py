"""Tests for CLI flag wiring fixes (side indexes, no-color, multi-site, index-files)."""

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from doc_search.cli import commands
from doc_search.cli.commands import (
    _remove_side_indexes,
    _side_index_paths,
    cmd_index,
    cmd_search_all,
)
from doc_search.indexer import BM25Index
from doc_search.multi_search import MultiSiteSearchEngine


def _write_page(pages_dir: Path, name: str, title: str, text: str, url: str = None):
    pages_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        'url': url or f'https://example.com/{name}',
        'title': title,
        'text': text,
        'headings': [[1, title]],
        'description': '',
    }
    (pages_dir / f'{name}.json').write_text(json.dumps(doc), encoding='utf-8')


def test_remove_side_indexes_deletes_known_extensions(tmp_path):
    site = tmp_path / 'site'
    site.mkdir()
    for p in _side_index_paths(site, 'fuzzy'):
        p.write_text('x', encoding='utf-8')
    # only .json and .json.gz typically exist; write a couple
    removed = _remove_side_indexes(site, 'fuzzy', quiet=True)
    assert removed >= 2
    assert not any(p.exists() for p in _side_index_paths(site, 'fuzzy'))


def test_index_no_symspell_removes_existing_fuzzy(tmp_path, capsys):
    site = tmp_path / 'site'
    pages = site / 'pages'
    _write_page(pages, 'a', 'Python Tutorial', 'Learn python lists and tuples thoroughly.')
    _write_page(pages, 'b', 'Async Guide', 'async await coroutines and event loops.')

    # First build with side indexes
    args = argparse.Namespace(
        site_dir=str(site),
        k1=1.5,
        b=0.75,
        no_compress=True,
        no_stemming=False,
        no_symspell=False,
        no_ngram=False,
        no_suggestions=True,
        suggest_max_words=3,
        separate_paths=False,
        parser='dom',
        reparse=False,
        chunks=False,
        max_body_chars=200000,
        no_url_filter=False,
        full=True,
        quiet=True,
    )
    assert cmd_index(args) == 0
    fuzzy = site / 'fuzzy.json'
    assert fuzzy.exists() or (site / 'fuzzy.json.gz').exists()

    # Touch a fuzzy file explicitly for deterministic check
    fuzzy.write_text('{"stale": true}', encoding='utf-8')

    # Rebuild with --no-symspell
    args.no_symspell = True
    args.no_ngram = True
    assert cmd_index(args) == 0

    assert not fuzzy.exists()
    assert not (site / 'fuzzy.json.gz').exists()
    assert not (site / 'ngram.json').exists()
    assert not (site / 'ngram.json.gz').exists()

    # Main index still present
    assert any((site / name).exists() for name in ('index.json', 'index.json.gz', 'index.pkl.gz', 'index.pkl'))


def test_index_parser_without_reparse_warns(tmp_path, capsys):
    site = tmp_path / 'site'
    pages = site / 'pages'
    _write_page(pages, 'a', 'Hello', 'hello world document content here')
    args = argparse.Namespace(
        site_dir=str(site),
        k1=1.5,
        b=0.75,
        no_compress=True,
        no_stemming=False,
        no_symspell=True,
        no_ngram=True,
        no_suggestions=True,
        suggest_max_words=3,
        separate_paths=False,
        parser='stream',
        reparse=False,
        chunks=False,
        max_body_chars=200000,
        no_url_filter=False,
        full=True,
        quiet=False,
    )
    assert cmd_index(args) == 0
    out = capsys.readouterr().out
    assert '--parser=stream has no effect without --reparse' in out


def test_multi_site_engine_respects_feature_flags(tmp_path):
    """Constructor kwargs must reach EnhancedSearchEngine.load."""
    sites = [{
        'path': tmp_path / 's',
        'url': 'https://example.com',
        'name': 'ex',
        'hash': 's',
        'index_path': tmp_path / 's' / 'index.json',
    }]
    engine = MultiSiteSearchEngine(
        sites=sites,
        enable_symspell=True,
        enable_ngram=True,
        enable_synonyms=True,
    )
    assert engine._engine_kwargs['enable_symspell'] is True
    assert engine._engine_kwargs['enable_ngram'] is True
    assert engine._engine_kwargs['enable_synonyms'] is True

    with patch('doc_search.multi_search.EnhancedSearchEngine.load') as load:
        load.return_value = MagicMock()
        engine._get_engine(sites[0])
        load.assert_called_once()
        kwargs = load.call_args.kwargs
        assert kwargs['enable_symspell'] is True
        assert kwargs['enable_ngram'] is True
        assert kwargs['enable_synonyms'] is True


def test_search_all_no_color_avoids_ansi(tmp_path, capsys, monkeypatch):
    """--no-color should not emit ANSI style codes in text output."""
    # Build a tiny multi-site layout
    sites_root = tmp_path / 'sites'
    site_a = sites_root / 'site_a'
    pages = site_a / 'pages'
    _write_page(pages, 'p1', 'Alpha Docs', 'alpha bravo charlie search term unique_xyz')
    idx = BM25Index()
    idx.build_from_pages(pages, verbose=False)
    idx.save(site_a / 'index.json', compress=False)
    (site_a / 'metadata.json').write_text(
        json.dumps({'url': 'https://a.example.com', 'site_name': 'A'}),
        encoding='utf-8',
    )

    monkeypatch.setattr(commands, 'DEFAULT_DATA_DIR', sites_root)
    # multi_search imports DEFAULT_DATA_DIR at module level
    import doc_search.multi_search as ms
    monkeypatch.setattr(ms, 'DEFAULT_DATA_DIR', sites_root)

    args = argparse.Namespace(
        query='unique_xyz',
        limit=5,
        sites=None,
        scores=False,
        json=False,
        quiet=True,
        no_color=True,
        symspell=False,
        ngram=False,
        synonyms=False,
    )
    rc = cmd_search_all(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert '\x1b[' not in out  # no ANSI escapes
    assert 'unique_xyz' in out or 'Alpha' in out or 'result' in out.lower()


def test_index_files_namespace_plumbs_flags(tmp_path, monkeypatch):
    """cmd_index_files should pass no_symspell/no_ngram into cmd_index."""
    # Create a tiny html file set
    src = tmp_path / 'docs'
    src.mkdir()
    (src / 'a.html').write_text('<html><body><h1>Hi</h1><p>content body text</p></body></html>', encoding='utf-8')

    captured = {}

    def fake_cmd_index(index_args):
        captured.update(vars(index_args))
        return 0

    monkeypatch.setattr(commands, 'cmd_index', fake_cmd_index)
    monkeypatch.setattr(commands, 'DEFAULT_DATA_DIR', tmp_path / 'data')
    (tmp_path / 'data').mkdir()

    args = argparse.Namespace(
        directory=str(src),
        extensions='html',
        no_recursive=True,
        exclude=None,
        site_name='t',
        merge_with=None,
        no_headers=False,
        max_rows=None,
        quiet=True,
        force=True,
        clean=False,
        no_symspell=True,
        no_ngram=True,
        no_suggestions=True,
        k1=1.2,
        b=0.5,
        no_compress=True,
        no_stemming=True,
        suggest_max_words=2,
        chunks=True,
        max_body_chars=1000,
        no_url_filter=True,
        parser='dom',
        reparse=False,
    )
    rc = commands.cmd_index_files(args)
    assert rc == 0
    assert captured.get('no_symspell') is True
    assert captured.get('no_ngram') is True
    assert captured.get('no_suggestions') is True
    assert captured.get('k1') == 1.2
    assert captured.get('chunks') is True
