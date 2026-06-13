import importlib.util
import sys
from pathlib import Path


def _load_repair_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "repair_leaked_json.py"
    spec = importlib.util.spec_from_file_location("repair_leaked_json", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["repair_leaked_json"] = module
    spec.loader.exec_module(module)
    return module


def test_looks_like_jsonish_text_field_detects_single_summary_blob():
    repair = _load_repair_module()
    assert repair._looks_like_jsonish_text_field('{"summary":"Tekst"}') is True
    assert repair._looks_like_jsonish_text_field("Obican tekst.") is False


def test_clean_leaked_json_string_unwraps_truncated_summary():
    repair = _load_repair_module()
    leaked = '{"summary":"Izvestaj austrijskog dnevnika *Standard* ukazuje na duboke veze'
    data = repair._clean_leaked_json_string(leaked)
    assert data["summary"] == "Izvestaj austrijskog dnevnika *Standard* ukazuje na duboke veze"
