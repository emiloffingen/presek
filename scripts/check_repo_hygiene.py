#!/usr/bin/env python3
"""Fail when generated or local-only artifacts are tracked by git."""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

BLOCKED_PATTERNS = (
    "*/__pycache__/*",
    "__pycache__/*",
    "*.py[cod]",
    ".pytest_cache/*",
    ".ruff_cache/*",
    ".mypy_cache/*",
    ".cache/*",
    "*.db",
    "*.sqlite",
    "*.db-shm",
    "*.db-wal",
    "*.db.bak",
    "*.pem",
    "*.key",
    "*.crt",
    "*.cert",
    "*.log",
    "logs/*",
    "screenshots/*",
    "previews/*",
    "web/screenshots/*",
    "web/cypress/screenshots/*",
    "web/dist/*",
    "web/node_modules/*",
    "static/uploads/*",
    "static/generated/*",
    "digests/*",
)

ALLOWED_PATHS = frozenset(
    {
        "web/package-lock.json",
    }
)


def tracked_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line]


def find_blocked_tracked_files(paths: list[str]) -> list[str]:
    blocked: list[str] = []
    for path in paths:
        if path in ALLOWED_PATHS:
            continue
        if any(fnmatch.fnmatch(path, pattern) for pattern in BLOCKED_PATTERNS):
            blocked.append(path)
    return sorted(blocked)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to inspect.",
    )
    args = parser.parse_args(argv)

    blocked = find_blocked_tracked_files(tracked_files(args.repo_root))
    if blocked:
        print("Generated or local-only files are tracked:", file=sys.stderr)
        for path in blocked:
            print(f"  - {path}", file=sys.stderr)
        return 1

    print("Repo hygiene check passed: no generated/local artifacts are tracked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
