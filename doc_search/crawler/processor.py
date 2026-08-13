from ..crawl import processor as _impl
import sys
sys.modules[__name__] = _impl
