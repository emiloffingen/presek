# Macedonian to Serbian Migration Plan

## Objectives
- Transition the codebase from Macedonian (MK) to Serbian (SR).
- Replace MK-specific logic with generic or SR-specific alternatives.
- Ensure all NLP, routing, and UI components support the new target language.

## Migration Phases

### Phase 1: Automated Translation
- Apply `scripts/translate_mk_to_sr.py --apply` to all files.
- Validate the changes with existing tests.

### Phase 2: Logic Refactoring (NLP & Routing)
- Replace `rewrite_to_macedonian_locally` in `nlp/text_processing.py` and `nlp/__init__.py`.
- Update `routes/common.py`: `_looks_macedonian_headline` -> `_looks_serbian_headline` (or a more generic `_looks_cyrillic_headline`).
- Update `nlp/categories.py`, `nlp/keywords.py`, and `nlp/sentiment.py` to support Serbian lexicon and categorizations.

### Phase 3: System Component Updates
- Update database migrations and schema references (if any exist, like table naming conventions).
- Update tasks/intelligence.py detection logic.

### Phase 4: UI/UX Updates
- Audit `web/src/components` and `web/src/pages` for hardcoded Macedonian UI strings.
- Update `web/src/utils/briefingFormatter.ts` and `web/src/utils/textUtils.ts` for Serbian linguistic rules.

### Phase 5: Verification & Cleanup
- Run full test suite.
- Remove redundant MK-specific code.
- Update documentation in `README.md` and `DESIGN.md`.
