from ..crawl import crawler as _impl
import sys
sys.modules[__name__] = _impl
