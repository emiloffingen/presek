"""Backwards-compatible re-exports — prefer core.copy_quality."""

from core.copy_quality import (  # noqa: F401
    assess_mk_copy_purity,
    mk_bundle_passes_publish_gate,
    mk_copy_passes_publish_gate,
)
