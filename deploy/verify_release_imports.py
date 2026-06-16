#!/usr/bin/env python3
"""Verify that release-critical Python modules import cleanly."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "deploy" / "python_env_contract.json"

# Import-time guards (e.g. routes.security) require these even for smoke imports.
os.environ.setdefault("CSRF_TOKEN_SECRET", "release-import-check")
os.environ.setdefault("ENV", "test")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_required_modules() -> tuple[str, ...]:
    if not CONTRACT_PATH.is_file():
        return (
            "core.api_fast",
            "core.health",
            "tasks.intelligence.synthesis",
            "tasks.intelligence.synthesis_pipeline",
            "tasks.delivery.briefing",
        )
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    modules: list[str] = []
    seen: set[str] = set()
    for key in ("runtime_imports", "worker_runtime_imports"):
        for name in contract.get(key) or []:
            if name not in seen:
                seen.add(name)
                modules.append(name)
    # Extra modules exercised by split packages but not listed in the contract yet.
    for extra in (
        "core.synthesis_quality",
        "core.synthesis_trace",
        "core.personalization_score",
        "tasks.intelligence.synthesis_persist",
        "tasks.intelligence.synthesis_generation",
        "tasks.intelligence.synthesis_grounding",
        "tasks.intelligence.synthesis_translation",
        "tasks.intelligence.synthesis_bundle",
        "tasks.intelligence.synthesis_merge",
        "tasks.intelligence.synthesis_scheduling",
        "tasks.delivery.briefing_quality",
        "tasks.delivery.briefing_alerts",
    ):
        if extra not in seen:
            seen.add(extra)
            modules.append(extra)
    return tuple(modules)


REQUIRED_MODULES = _load_required_modules()


def main() -> int:
    failures: list[str] = []
    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - exercised via test
            failures.append(f"{module_name}: {exc}")

    if failures:
        print("Release import verification failed:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"Release import verification passed ({len(REQUIRED_MODULES)} modules).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
