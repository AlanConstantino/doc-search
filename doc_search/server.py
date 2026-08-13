from .app import server as _impl
import sys
sys.modules[__name__] = _impl
