import json
from pathlib import Path

from scripts.check_api_venv_imports import load_contract, scan_forbidden_top_level_imports

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "deploy" / "python_env_contract.json"


def test_api_contract_has_no_forbidden_top_level_imports():
    contract = load_contract()
    violations = scan_forbidden_top_level_imports(contract)
    assert not violations, "Forbidden top-level imports in API surface:\n" + "\n".join(violations)


def test_queue_status_does_not_import_worker_tasks():
    import sys

    before = set(sys.modules)

    for name in list(sys.modules):
        if name == "core.queue_status" or name.startswith("core.queue_status."):
            del sys.modules[name]

    import core.queue_status  # noqa: F401

    newly_loaded = set(sys.modules) - before
    task_imports = sorted(name for name in newly_loaded if name.startswith("tasks."))
    assert not task_imports, f"queue_status import pulled in worker tasks: {task_imports}"


def test_api_contract_file_declares_split_venv_groups():
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert data["api_dependency_groups"] == ["api"]
    assert data["worker_dependency_groups"] == ["api", "worker"]
    assert "llama_cpp" in data["forbidden_modules"]
