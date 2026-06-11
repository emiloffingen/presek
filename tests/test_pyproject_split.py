"""Verify Phase 4 dependency isolation between API and worker groups."""

import re
from pathlib import Path

import tomllib


def _load_pyproject() -> dict:
    return tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))


def _package_names(specs: list[str]) -> set[str]:
    names: set[str] = set()
    for spec in specs:
        name = spec.split("@", 1)[0].strip().split("[", 1)[0].strip()
        name = re.split(r"[<>=!~]", name, maxsplit=1)[0].strip().lower()
        names.add(name)
    return names


def test_api_group_excludes_heavy_worker_packages():
    data = _load_pyproject()
    api = _package_names(data["dependency-groups"]["api"])
    worker = _package_names(data["dependency-groups"]["worker"])

    heavy = {"torch", "spacy", "llama-cpp-python", "playwright", "keybert", "omnivoice", "gtts", "edge-tts"}
    assert heavy.isdisjoint(api), f"API group should not include worker ML packages: {heavy & api}"
    assert heavy.issubset(worker)


def test_worker_group_includes_intelligence_stack():
    data = _load_pyproject()
    worker = _package_names(data["dependency-groups"]["worker"])
    assert {"torch", "spacy", "playwright"}.issubset(worker)


def test_base_dependencies_exclude_web_and_ml_stacks():
    data = _load_pyproject()
    base = _package_names(data["project"]["dependencies"])
    assert "fastapi" not in base
    assert "torch" not in base
    assert "celery" in base
    assert "psycopg" in base


def test_uv_default_groups_include_api_and_worker():
    data = _load_pyproject()
    assert data["tool"]["uv"]["default-groups"] == ["api", "worker"]
