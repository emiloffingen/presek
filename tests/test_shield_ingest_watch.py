"""host/shield_ingest_watch.sh: daytime 45 min limit, relaxed limit overnight (UTC)."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "host" / "shield_ingest_watch.sh"

STUB_CURL = """#!/bin/sh
out=""; while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done
printf '{"freshness":{"age_minutes":%s}}' "$AGE" > "$out"; printf 200
"""


def _run(tmp_path, age, hour):
    stub = tmp_path / "curl"
    stub.write_text(STUB_CURL)
    stub.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "AGE": str(age),
        "HOUR_UTC": hour,
        "LOG": str(tmp_path / "watch.log"),
        "TMPDIR": str(tmp_path),
        "DRY": "1",
        "ONCE": "1",
        "BAD_NEEDED": "1",
    }
    out = subprocess.run(["sh", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30).stdout
    return "INGESTION STALE" in out


@pytest.mark.parametrize(
    "age,hour,alerts",
    [
        (66, "12", True),  # daytime: 66 min without articles is a real problem
        (50, "08", True),  # "08" must not be parsed as octal
        (50, "05", True),  # 05:00 UTC is already daytime
        (66, "03", False),  # the 2026-10-17 false alarm: quiet night
        (105, "01", False),  # longest natural gap seen in 72 h
        (149, "22", False),
        (160, "03", True),  # even at night, 160 min is too long
        (50, "00", False),  # "00" hour
        (50, "04", False),
    ],
)
def test_threshold_depends_on_time_of_day(tmp_path, age, hour, alerts):
    assert _run(tmp_path, age, hour) is alerts
