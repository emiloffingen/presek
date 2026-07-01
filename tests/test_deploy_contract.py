import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "deploy" / "python_env_contract.json"
VERIFY_SCRIPT = ROOT / "deploy" / "verify_release_imports.py"


def test_python_env_contract_lists_synthesis_modules():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    worker_imports = contract.get("worker_runtime_imports") or []
    combined = "\n".join(worker_imports)
    for fragment in (
        "synthesis_pipeline",
        "synthesis_persist",
        "briefing_quality",
    ):
        assert fragment in combined


def test_verify_release_imports_script_passes():
    env = os.environ.copy()
    env.setdefault("CSRF_TOKEN_SECRET", "release-import-check")
    env.setdefault("ENV", "test")
    result = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_verify_release_imports_reads_contract_modules():
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert "python_env_contract.json" in script
    assert "worker_runtime_imports" in script


@pytest.mark.parametrize(
    "service_name",
    [
        "presek-worker-synthesis.service",
        "presek-worker-fasttrack.service",
        "presek-worker-maintenance.service",
    ],
)
def test_split_worker_units_have_hardening(service_name: str):
    content = (ROOT / "deploy" / "systemd" / service_name).read_text(encoding="utf-8")
    assert "ProtectSystem=strict" in content
    assert "MemoryMax=" in content
    assert "--queues=" in content
