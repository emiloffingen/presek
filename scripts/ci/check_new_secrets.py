#!/usr/bin/env python3
"""Fail if the working tree contains secret candidates not already in .secrets.baseline.

Run after `detect-secrets scan --baseline .secrets.baseline` has refreshed the file.
Compares (file, hashed_secret) against the committed baseline, so edits that only
move a known false positive to another line do not fail the check.
"""

import json
import subprocess
import sys

BASELINE = ".secrets.baseline"


def fingerprints(results: dict) -> dict:
    return {(path, r["hashed_secret"]): (r["type"], r["line_number"]) for path, rs in results.items() for r in rs}


current = fingerprints(json.load(open(BASELINE))["results"])
committed_raw = subprocess.run(["git", "show", f"HEAD:{BASELINE}"], capture_output=True, text=True, check=True).stdout
committed = fingerprints(json.loads(committed_raw)["results"])

new = sorted((path, kind, line) for (path, h), (kind, line) in current.items() if (path, h) not in committed)
if new:
    print(f"::error::{len(new)} new secret candidate(s). Remove them, or if they are false positives run")
    print("::error::`uvx detect-secrets==1.5.0 scan --baseline .secrets.baseline` and commit the baseline.")
    for path, kind, line in new:
        print(f"::error file={path},line={line}::{kind}")
    sys.exit(1)
print(f"No new secret candidates ({len(current)} known entries in {BASELINE}).")
