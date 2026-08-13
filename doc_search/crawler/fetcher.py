from ..crawl import fetcher as _impl
import sys
sys.modules[__name__] = _impl
