import os
import subprocess
from pathlib import Path


_ROOT = Path(__file__).resolve().parent
_VERSION_FILE = _ROOT / "VERSION"


def _read_version_file() -> str:
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


APP_VERSION = (os.environ.get("PRESEK_VERSION") or _read_version_file()).strip() or "0.0.0"
APP_VERSION_LABEL = APP_VERSION.removesuffix(".0")


def _git_sha() -> str | None:
    env_sha = (os.environ.get("PRESEK_GIT_SHA") or os.environ.get("GIT_COMMIT") or "").strip()
    if env_sha:
        return env_sha[:12]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def version_payload() -> dict:
    payload = {
        "version": APP_VERSION,
        "version_label": APP_VERSION_LABEL,
    }
    release = (os.environ.get("PRESEK_RELEASE") or os.environ.get("RELEASE_ID") or "").strip()
    if release:
        payload["release"] = release
    sha = _git_sha()
    if sha:
        payload["commit"] = sha
    return payload
