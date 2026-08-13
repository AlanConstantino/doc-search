"""Document extractor registry.

Crawl and CLI talk to this module instead of importing concrete extractors.
Adding a format means registering it here — not editing the crawler.
"""

from typing import Any, Dict, List, Optional, Tuple


# (suffix, content-type needles, log emoji, log label, stat key)
_KIND_META = {
    'pdf':  ('.pdf',  ('application/pdf',), '📄', 'PDF', 'docs_pdf'),
    'docx': ('.docx', ('wordprocessingml', 'application/vnd.openxmlformats-officedocument.wordprocessingml'), '📝', 'Word', 'docs_docx'),
    'xlsx': ('.xlsx', ('spreadsheetml', 'application/vnd.openxmlformats-officedocument.spreadsheetml'), '📊', 'Excel', 'docs_xlsx'),
    'pptx': ('.pptx', ('presentationml', 'application/vnd.openxmlformats-officedocument.presentationml'), '📽️', 'PowerPoint', 'docs_pptx'),
}


class ExtractorRegistry:
    """Lazy factory for PDF / Office extractors used during crawl and index-files."""

    def __init__(
        self,
        timeout: float = 30.0,
        user_agent: str = "DocSearchBot/1.2",
        auth: Optional[Tuple[str, str]] = None,
        auth_token: Optional[str] = None,
    ):
        self.timeout = timeout
        self.user_agent = user_agent
        self.auth = auth
        self.auth_token = auth_token
        self._instances: Dict[str, Any] = {}

    def get(self, kind: str):
        """Return the extractor instance for ``kind`` (pdf/docx/xlsx/pptx)."""
        kind = kind.lower()
        if kind not in self._instances:
            self._instances[kind] = self._build(kind)
        return self._instances[kind]

    def _build(self, kind: str):
        if kind == 'pdf':
            from .pdf import PDFExtractor
            return PDFExtractor(
                timeout=self.timeout,
                user_agent=self.user_agent,
                auth=self.auth,
                auth_token=self.auth_token,
            )
        if kind == 'docx':
            from .word import WordExtractor
            return WordExtractor()
        if kind == 'xlsx':
            from .excel import ExcelExtractor
            return ExcelExtractor()
        if kind == 'pptx':
            from .pptx import PPTXExtractor
            return PPTXExtractor()
        raise KeyError("unknown extractor kind: %r" % kind)

    @staticmethod
    def kind_from_path(path: str) -> Optional[str]:
        lower = (path or '').lower()
        for kind, (suffix, _needles, _e, _label, _stat) in _KIND_META.items():
            if lower.endswith(suffix):
                return kind
        return None

    @staticmethod
    def kind_from_content_type(content_type: str, url: str = '') -> Optional[str]:
        ct = (content_type or '').lower()
        lower_url = (url or '').lower()
        for kind, (suffix, needles, _e, _label, _stat) in _KIND_META.items():
            if any(n in ct for n in needles) or lower_url.endswith(suffix):
                return kind
        return None

    @staticmethod
    def meta(kind: str) -> Dict[str, str]:
        suffix, _needles, emoji, label, stat = _KIND_META[kind]
        return {
            'suffix': suffix,
            'emoji': emoji,
            'label': label,
            'stat': stat,
        }


def create_registry(
    timeout: float = 30.0,
    user_agent: str = "DocSearchBot/1.2",
    auth: Optional[Tuple[str, str]] = None,
    auth_token: Optional[str] = None,
) -> ExtractorRegistry:
    return ExtractorRegistry(
        timeout=timeout,
        user_agent=user_agent,
        auth=auth,
        auth_token=auth_token,
    )
