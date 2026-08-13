from .core import config as _impl
import sys
sys.modules[__name__] = _impl
