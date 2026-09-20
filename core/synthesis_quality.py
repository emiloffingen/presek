"""Stub: synthesis quality removed in mk-only simplify."""


def build_synthesis_meta(*a, **kw): return {}
def synthesis_needs_upgrade(*a, **kw): return False
def list_stuck_fast_synthesis_cluster_ids(*a, **kw): return []
def prune_stale_fast_synthesis_pending(*a, **kw): return 0
def count_low_score_syntheses(*a, **kw): return 0
def count_stuck_fast_syntheses(*a, **kw): return 0
def count_upgradeable_syntheses(*a, **kw): return {"provisional_count": 0, "fallback_count": 0}
def count_synthesis_persist_gap(*a, **kw): return {"synthesis_events": 0, "db_persisted_events": 0, "persist_gap": 0}
