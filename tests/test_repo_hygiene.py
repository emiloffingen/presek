from pathlib import Path

from scripts.check_repo_hygiene import find_blocked_tracked_files, tracked_files


def test_hygiene_patterns_catch_local_artifacts():
    paths = [
        "core/__pycache__/api_fast.cpython-313.pyc",
        "core/database.db",
        "private_key.pem",
        "screenshots/homepage.png",
        "web/dist/server/entry.mjs",
        "web/node_modules/.package-lock.json",
        "web/package-lock.json",
    ]

    assert find_blocked_tracked_files(paths) == [
        "core/__pycache__/api_fast.cpython-313.pyc",
        "core/database.db",
        "private_key.pem",
        "screenshots/homepage.png",
        "web/dist/server/entry.mjs",
        "web/node_modules/.package-lock.json",
    ]


def test_repo_has_no_tracked_generated_or_local_artifacts():
    repo_root = Path(__file__).resolve().parents[1]
    assert find_blocked_tracked_files(tracked_files(repo_root)) == []
