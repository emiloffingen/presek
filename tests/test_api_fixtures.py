import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "home_api_sample.json"


def test_home_api_fixture_contract_keys():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for key in (
        "status",
        "lead",
        "supporting",
        "developing",
        "wire",
        "stats",
        "lead_display",
        "pipeline",
    ):
        assert key in payload
