"""ANSI / emoji helpers for the CLI and formatted search output.

Crawl, index, and extract must not import this module.
"""

import json as _json
import os
import sys
from pathlib import Path


def _enable_windows_ansi() -> bool:
    """
    Enable ANSI escape code support on Windows 10+.
    
    Windows 10 version 1607+ supports ANSI via Virtual Terminal Processing,
    but it must be explicitly enabled on the console output handle.
    
    Returns:
        True if colors are supported (or not on Windows), False otherwise.
    """
    if sys.platform != 'win32':
        return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    
    if not (hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()):
        return False
    
    try:
        import ctypes
        from ctypes import wintypes
        
        kernel32 = ctypes.windll.kernel32
        
        # STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(wintypes.DWORD(-11))
        if handle == wintypes.HANDLE(-1).value:
            return False
        
        # Get current console mode
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        ENABLE_VTP = 0x0004
        if not (mode.value & ENABLE_VTP):
            # Try to enable it
            if not kernel32.SetConsoleMode(handle, wintypes.DWORD(mode.value | ENABLE_VTP)):
                return False
        
        return True
    except (AttributeError, ImportError, OSError, ValueError):
        # ctypes or windll not available, or console API failed
        return False



# Emoji fallbacks (DOC_SEARCH_NO_EMOJI=1 → ASCII)
_NO_EMOJI = os.environ.get('DOC_SEARCH_NO_EMOJI', '').lower() in ('1', 'true', 'yes')
_EMOJI_MAP = {
    'search': ('🔍', '[*]'),
    'docs': ('📄', '[-]'),
    'terms': ('🔤', '[#]'),
    'check': ('✓', '+'),
    'cross': ('✗', 'x'),
    'bulb': ('💡', '*'),
    'moon': ('🌙', '[D]'),
    'sun': ('☀️', '[L]'),
    'palette': ('🎨', ''),
    'books': ('📚', '[=]'),
    'chart': ('📊', '#'),
    'globe': ('🌐', '@'),
    'folder': ('📁', '>'),
    'ruler': ('📏', 'A:'),
    'sparkles': ('✨', '*'),
    'skip': ('⏭', '-'),
}


def emoji(name: str) -> str:
    """Get emoji or ASCII fallback based on DOC_SEARCH_NO_EMOJI env var."""
    pair = _EMOJI_MAP.get(name, ('', ''))
    return pair[1] if _NO_EMOJI else pair[0]

class Colors:
    """ANSI escape codes for terminal colors and styles."""
    
    # Check if terminal supports colors (enables VTP on Windows 10+)
    _supports_color = _enable_windows_ansi()
    
    # Reset
    RESET = '\033[0m' if _supports_color else ''
    
    # Styles
    BOLD = '\033[1m' if _supports_color else ''
    DIM = '\033[2m' if _supports_color else ''
    ITALIC = '\033[3m' if _supports_color else ''
    UNDERLINE = '\033[4m' if _supports_color else ''
    
    # Foreground colors
    BLACK = '\033[30m' if _supports_color else ''
    RED = '\033[31m' if _supports_color else ''
    GREEN = '\033[32m' if _supports_color else ''
    YELLOW = '\033[33m' if _supports_color else ''
    BLUE = '\033[34m' if _supports_color else ''
    MAGENTA = '\033[35m' if _supports_color else ''
    CYAN = '\033[36m' if _supports_color else ''
    WHITE = '\033[37m' if _supports_color else ''
    
    # Bright foreground colors
    BRIGHT_BLACK = '\033[90m' if _supports_color else ''
    BRIGHT_RED = '\033[91m' if _supports_color else ''
    BRIGHT_GREEN = '\033[92m' if _supports_color else ''
    BRIGHT_YELLOW = '\033[93m' if _supports_color else ''
    BRIGHT_BLUE = '\033[94m' if _supports_color else ''
    BRIGHT_MAGENTA = '\033[95m' if _supports_color else ''
    BRIGHT_CYAN = '\033[96m' if _supports_color else ''
    BRIGHT_WHITE = '\033[97m' if _supports_color else ''
    
    # Extended colors (256-color)
    ORANGE = '\033[38;5;208m' if _supports_color else ''
    
    @classmethod
    def disable(cls):
        """Disable all colors."""
        for attr in dir(cls):
            if attr.isupper() and not attr.startswith('_'):
                setattr(cls, attr, '')
    
    @classmethod
    def enable(cls):
        """Re-enable colors if terminal supports them."""
        if _enable_windows_ansi():
            cls._supports_color = True
            # Re-apply colors
            cls.RESET = '\033[0m'
            cls.BOLD = '\033[1m'
            cls.DIM = '\033[2m'
            cls.ITALIC = '\033[3m'
            cls.UNDERLINE = '\033[4m'
            cls.BLACK = '\033[30m'
            cls.RED = '\033[31m'
            cls.GREEN = '\033[32m'
            cls.YELLOW = '\033[33m'
            cls.BLUE = '\033[34m'
            cls.MAGENTA = '\033[35m'
            cls.CYAN = '\033[36m'
            cls.WHITE = '\033[37m'
            cls.BRIGHT_BLACK = '\033[90m'
            cls.BRIGHT_RED = '\033[91m'
            cls.BRIGHT_GREEN = '\033[92m'
            cls.BRIGHT_YELLOW = '\033[93m'
            cls.BRIGHT_BLUE = '\033[94m'
            cls.BRIGHT_MAGENTA = '\033[95m'
            cls.BRIGHT_CYAN = '\033[96m'
            cls.BRIGHT_WHITE = '\033[97m'


def colorize(text: str, *styles) -> str:
    """Apply color/style codes to text."""
    if not styles:
        return text
    return ''.join(styles) + text + Colors.RESET


def _hex_to_ansi(hex_color: str) -> str:
    """Convert a hex color like '#FF5733' to an ANSI true color escape code."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return ''
    try:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f'\033[38;2;{r};{g};{b}m'
    except ValueError:
        return ''


_STYLE_MAP = {
    'bold': '\033[1m',
    'dim': '\033[2m',
    'italic': '\033[3m',
    'underline': '\033[4m',
}


def _parse_color_value(value: str) -> tuple:
    """
    Parse a color value like '#FF5733+bold+underline' into ANSI codes.
    
    Returns:
        Tuple of ANSI escape code strings
    """
    if not value or not Colors._supports_color:
        return ()
    
    parts = value.split('+')
    codes = []
    
    # First part is the hex color
    hex_part = parts[0].strip()
    if hex_part.startswith('#'):
        ansi = _hex_to_ansi(hex_part)
        if ansi:
            codes.append(ansi)
    
    # Remaining parts are style modifiers
    for part in parts[1:]:
        style = _STYLE_MAP.get(part.strip().lower(), '')
        if style:
            codes.append(style)
    
    return tuple(codes)


def _load_color_theme() -> dict:
    """
    Load CLI color theme from colors.json.
    
    Searches in order:
    1. ~/.doc_search/colors.json (user override)
    2. Bundled data/colors.json (defaults)
    
    Returns:
        Dict mapping role names to hex color strings
    """
    import json as _json
    
    # User override
    user_path = Path.home() / '.doc_search' / 'colors.json'
    if user_path.exists():
        try:
            with open(user_path, encoding='utf-8') as f:
                return _json.load(f)
        except (_json.JSONDecodeError, IOError):
            pass
    
    # Bundled defaults
    default_path = Path(__file__).resolve().parent.parent / 'core' / 'data' / 'colors.json'
    if default_path.exists():
        try:
            with open(default_path, encoding='utf-8') as f:
                return _json.load(f)
        except (_json.JSONDecodeError, IOError):
            pass
    
    return {}


def _resolve_styles(role: str) -> tuple:
    """Resolve a role name to ANSI escape codes from the color theme."""
    value = _COLOR_THEME.get(role, '')
    if not value or isinstance(value, list):
        # Fallback for old list format or empty
        return ()
    return _parse_color_value(value)


# Load theme once at import time
_COLOR_THEME = _load_color_theme()


def highlight_match(text: str) -> str:
    """Highlight a matched term."""
    return colorize(text, *_resolve_styles('highlight'))


def style_title(text: str) -> str:
    """Style a title."""
    return colorize(text, *_resolve_styles('title'))


def style_url(text: str) -> str:
    """Style a URL."""
    return colorize(text, *_resolve_styles('url'))


def style_score(score: float) -> str:
    """Style a score."""
    return colorize(f"[{score:.4f}]", *_resolve_styles('score'))


def style_number(num: int) -> str:
    """Style a result number."""
    return colorize(f"{num}.", *_resolve_styles('number'))


def style_info(text: str) -> str:
    """Style info text."""
    return colorize(text, *_resolve_styles('info'))


def style_success(text: str) -> str:
    """Style success text."""
    return colorize(text, *_resolve_styles('success'))


def style_error(text: str) -> str:
    """Style error text."""
    return colorize(text, *_resolve_styles('error'))

