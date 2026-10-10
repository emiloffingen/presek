import re

from core.database import db_manager as db


def has_latin(text):
    if not text:
        return False
    # Check for Latin characters (A-Z)
    return bool(re.search(r"[A-Za-z]", text))


def check():
    rows = db.execute(
        "SELECT cluster_id, lang, summary, generated_article FROM cluster_summaries WHERE lang = 'mk' AND created_at >= NOW() - INTERVAL '48 hours'"
    )
    print(f"Checked {len(rows)} recent Macedonian summaries.")
    mixed = []
    for r in rows:
        if has_latin(r["summary"]) or has_latin(r["generated_article"]):
            mixed.append(r["cluster_id"])

    print(f"Found {len(mixed)} mixed (Latin in Cyrillic) summaries on MK site: {mixed}")


if __name__ == "__main__":
    check()
