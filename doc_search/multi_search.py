from .search import multi as _impl
import sys
sys.modules[__name__] = _impl
