import logging
import os
import sys

sys.path.insert(0, "/home/emiloffingen/presek")
os.environ["VIBE_HOME"] = "/home/emiloffingen/presek"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)

from core.ai_engine import sync_call_ai as _call_ai
from core.prompts import DAILY_BRIEF_SYSTEM_PROMPT, DAILY_BRIEF_SYSTEM_PROMPT_MK
from tasks.delivery.briefing import _build_daily_brief_context, _load_daily_brief_clusters, _resolve_briefing_date
from tasks.delivery.briefing_quality import (
    _has_valid_daily_brief_structure,
    _is_grounded_daily_brief,
    _is_high_quality_briefing,
)


def run_test(lang="sr"):
    print(f"\n==================== Testing Briefing Generation for {lang} ====================")
    target_date = _resolve_briefing_date(None)
    clusters = _load_daily_brief_clusters(limit=10, lang=lang, briefing_date=target_date)
    print(f"Loaded {len(clusters)} clusters for {lang}")
    if not clusters:
        print("No clusters found!")
        return

    content_context = _build_daily_brief_context(clusters, lang=lang)

    # Simple system insight
    system_insight = "\n\n[SISTEMSKA ANALIZA ZA POSLEDNJIH 24 SATA]\n- Obradjeni clanci: 100\n- Udeo svetskih vest: 20%\n- Indeks pluralizma (raznovrsni izvori): 10%\n- Najzastupljeni akteri: Nema\n- U focusu lokacije: Balkan"
    full_context = f"<briefing_context>\n{content_context}\n{system_insight}\n</briefing_context>"
    prompt = DAILY_BRIEF_SYSTEM_PROMPT if lang == "sr" else DAILY_BRIEF_SYSTEM_PROMPT_MK

    print("Calling AI via nvidia...")
    brief, brief_provider = _call_ai(
        full_context,
        prompt,
        task_type="daily_brief",
        max_tokens=4000,
        lang=lang,
        provider_override="nvidia",
    )

    print(f"AI response received. Provider: {brief_provider}")
    if not brief:
        print("Error: AI returned empty response.")
        return

    print("\n--- AI Briefing Response Preview (first 500 chars) ---")
    print(brief[:500])
    print("-----------------------------------------------------")

    print("\nRunning Quality Gates:")
    valid_struct = _has_valid_daily_brief_structure(brief, lang=lang)
    print(f"1. Structure Valid: {valid_struct}")

    grounded = _is_grounded_daily_brief(brief, full_context)
    print(f"2. Grounded: {grounded}")

    high_quality = _is_high_quality_briefing(brief)
    print(f"3. High Quality: {high_quality}")


if __name__ == "__main__":
    run_test("sr")
    run_test("mk")
