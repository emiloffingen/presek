# Scripts

This directory is for operational helpers and manual checks that are useful to keep in the repo but should not be treated as part of the automated test suite.

## Manual Checks

- `manual_check_ai_cascade.py`
- `manual_check_cloudflare.py`
- `manual_check_keys.py`
- `manual_check_mistral.py`

These are intentionally ad hoc probes for provider behavior and credential validation. They are not CI-style tests and are not discovered by `pytest`.

## Utility Scripts

- `backfill_nlp.py`
- `show_ai_runtime_breakdown.py`

`backfill_nlp.py` is a manual maintenance helper for embedding/synthesis backfills.

`show_ai_runtime_breakdown.py` is a local inspection helper for runtime breakdown output.
