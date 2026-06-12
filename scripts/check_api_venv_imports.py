#!/usr/bin/env python3
"""Verify the API Python environment never depends on worker-only packages.

Usage (CI / production API venv):
  CSRF_TOKEN_SECRET=test ENV=test python scripts/check_api_venv_imports.py

Static-only (fast, no venv required):
  python scripts/check_api_venv_imports.py --static-only
"""
from __future__ import annotations

import argparse
import ast
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "deploy" / "python_env_contract.json"

DEFAULT_CONTRACT = {
    "forbidden_modules": ["llama_cpp", "torch", "playwright", "omnivoice"],
    "runtime_imports": ["nlp.local_analyst", "routes.news", "core.api_fast"],
    "static_scan_paths": [
        "routes",
        "core/api_fast.py",
        "nlp/local_analyst.py",
        "nlp/__init__.py",
    ],
}


def load_contract() -> dict:
    if not CONTRACT_PATH.is_file():
        return DEFAULT_CONTRACT
    with CONTRACT_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return {
        "forbidden_modules": list(data.get("forbidden_modules") or DEFAULT_CONTRACT["forbidden_modules"]),
        "runtime_imports": list(data.get("runtime_imports") or DEFAULT_CONTRACT["runtime_imports"]),
        "static_scan_paths": list(data.get("static_scan_paths") or DEFAULT_CONTRACT["static_scan_paths"]),
        "api_dependency_groups": list(data.get("api_dependency_groups") or ["api"]),
        "worker_dependency_groups": list(data.get("worker_dependency_groups") or ["api", "worker"]),
    }


def _iter_python_files(rel_paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for rel in rel_paths:
        path = ROOT / rel
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
        elif path.is_file():
            files.append(path)
    return files


def _module_root(name: str) -> str:
    return name.split(".", 1)[0]


def scan_forbidden_top_level_imports(contract: dict) -> list[str]:
    forbidden = {_module_root(item) for item in contract["forbidden_modules"]}
    violations: list[str] = []

    for path in _iter_python_files(contract["static_scan_paths"]):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{path.relative_to(ROOT)}: syntax error: {exc}")
            continue

        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = _module_root(alias.name)
                    if root in forbidden:
                        violations.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}: forbidden import `{alias.name}`"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = _module_root(node.module)
                    if root in forbidden:
                        violations.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}: forbidden import from `{node.module}`"
                        )

    return violations


def check_runtime_imports(contract: dict) -> list[str]:
    forbidden = set(contract["forbidden_modules"])
    errors: list[str] = []

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    for module_name in contract["runtime_imports"]:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            errors.append(f"failed to import {module_name}: {exc}")
            continue

        loaded = {name for name in sys.modules if name in forbidden or name.split(".", 1)[0] in forbidden}
        if loaded:
            errors.append(
                f"importing {module_name} loaded forbidden modules: {', '.join(sorted(loaded))}"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate API venv import contract")
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Only run AST scan (skip runtime imports)",
    )
    args = parser.parse_args()

    contract = load_contract()
    failures: list[str] = []

    static_violations = scan_forbidden_top_level_imports(contract)
    if static_violations:
        failures.extend(static_violations)

    if not args.static_only:
        failures.extend(check_runtime_imports(contract))

    if failures:
        print("API venv import contract FAILED:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1

    mode = "static" if args.static_only else "static+runtime"
    print(f"API venv import contract OK ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
