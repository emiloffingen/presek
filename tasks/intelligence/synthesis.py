"""Stub: tasks.intelligence.synthesis removed in mk-only simplify.

Re-export the registered no-op Celery task objects from the package so callers
that import from this submodule call ``.apply_async`` on a task object rather
than a plain function.
"""

from tasks.intelligence import (
    synthesize_cluster_task,
    synthesize_urgent_task,
    upgrade_fast_synthesis_task,
)

__all__ = [
    "synthesize_cluster_task",
    "synthesize_urgent_task",
    "upgrade_fast_synthesis_task",
]
