from .extract import pdf as _impl
import sys
sys.modules[__name__] = _impl
