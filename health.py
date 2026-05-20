"""Compatibility alias for legacy imports of ``health``.

The implementation lives in ``core.health``. Exposing the same module object
keeps older tests and patch targets such as ``health._get_redis`` working.
"""

import sys

from core import health as _health

sys.modules[__name__] = _health
