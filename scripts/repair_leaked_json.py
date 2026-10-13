#!/usr/bin/env python3
"""One-off backfill for AI JSON blobs leaked into reader-facing text fields."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.database import db_manager as db
from nlp.utils import extract_clean_summary_text, looks_like_leaked_json_fragment

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("repair_leaked_json")


def _looks_like_jsonish_text_field(text: str) -> bool:
    clean = str(text or "").strip()
    if not clean:
        return False
    if looks_like_leaked_json_fragment(clean):
        return True
    lowered = clean.lower()
    return clean.startswith("{") and ('"summary"' in lowered or '"text"' in lowered)


def _clean_leaked_json_string(text: str) -> dict:
    data: dict = {}
    if not text:
        return data

    clean = text.strip()
    lines = []
    for line in clean.splitlines():
        line_s = line.strip()
        if line_s.startswith("•"):
            line_s = line_s[1:].strip()
        lines.append(line_s)
    clean_lines = "\n".join(lines).strip()

    try:
        parsed = json.loads(clean_lines)
        if isinstance(parsed, dict):
            for key in ["synthetic_headline", "synthetic_standfirst", "summary", "generated_article", "key_facts"]:
                if key in parsed:
                    data[key] = parsed[key]
    except Exception:
        headline_match = re.search(r'"synthetic_headline"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_lines)
        if headline_match:
            try:
                data["synthetic_headline"] = (
                    headline_match.group(1).encode("utf-8").decode("unicode-escape", errors="ignore")
                )
            except Exception:
                data["synthetic_headline"] = headline_match.group(1)

        standfirst_match = re.search(r'"synthetic_standfirst"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_lines)
        if standfirst_match:
            try:
                data["synthetic_standfirst"] = (
                    standfirst_match.group(1).encode("utf-8").decode("unicode-escape", errors="ignore")
                )
            except Exception:
                data["synthetic_standfirst"] = standfirst_match.group(1)

        article_match = re.search(r'"generated_article"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_lines)
        if article_match:
            try:
                data["generated_article"] = (
                    article_match.group(1).encode("utf-8").decode("unicode-escape", errors="ignore")
                )
            except Exception:
                data["generated_article"] = article_match.group(1)

        summary_match = re.search(r'"summary"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_lines)
        if summary_match:
            try:
                data["summary"] = summary_match.group(1).encode("utf-8").decode("unicode-escape", errors="ignore")
            except Exception:
                data["summary"] = summary_match.group(1)
        else:
            truncated_summary = re.search(r'"summary"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)', clean_lines)
            if truncated_summary:
                try:
                    data["summary"] = (
                        truncated_summary.group(1).encode("utf-8").decode("unicode-escape", errors="ignore")
                    )
                except Exception:
                    data["summary"] = truncated_summary.group(1)

        summary_array_match = re.search(r'"summary"\s*:\s*\[(.*?)\]', clean_lines, re.DOTALL)
        if summary_array_match and "summary" not in data:
            array_content = summary_array_match.group(1)
            bullet_matches = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', array_content)
            bullets = []
            for bullet in bullet_matches:
                try:
                    bullets.append(bullet.encode("utf-8").decode("unicode-escape", errors="ignore"))
                except Exception:
                    bullets.append(bullet)
            if bullets:
                data["summary"] = bullets

    for key, value in list(data.items()):
        if isinstance(value, str):
            data[key] = value.replace('\\"', '"').replace("\\n", "\n").strip()
        elif isinstance(value, list):
            data[key] = [str(item).replace('\\"', '"').replace("\\n", "\n").strip() for item in value]

    return data


def _repair_cluster_row(row: dict, table_name: str, *, dry_run: bool) -> bool:
    summary_text = row.get("summary") or ""
    generated_article = row.get("generated_article") or ""

    summary_leaked = _looks_like_jsonish_text_field(summary_text)
    article_leaked = _looks_like_jsonish_text_field(generated_article)
    if not (summary_leaked or article_leaked):
        return False

    leaked_data = _clean_leaked_json_string(summary_text if summary_leaked else generated_article)
    if not leaked_data:
        log.warning(
            "Could not extract clean data from JSON fragment: cluster_id=%s lang=%s",
            row.get("cluster_id"),
            row.get("lang") or "sr",
        )
        return False

    headline = row.get("synthetic_headline") or ""
    standfirst = row.get("synthetic_standfirst") or ""
    new_headline = leaked_data.get("synthetic_headline") or headline
    new_standfirst = leaked_data.get("synthetic_standfirst") or standfirst
    new_article = leaked_data.get("generated_article") or row.get("generated_article")

    new_summary = summary_text
    if "summary" in leaked_data:
        if isinstance(leaked_data["summary"], list):
            new_summary = "\n".join(f"• {bullet}" for bullet in leaked_data["summary"])
        else:
            new_summary = str(leaked_data["summary"])
    elif summary_leaked:
        if leaked_data.get("synthetic_standfirst"):
            new_summary = str(leaked_data["synthetic_standfirst"])
        elif leaked_data.get("generated_article"):
            new_summary = str(leaked_data["generated_article"])

    cluster_id = row.get("cluster_id")
    lang = row.get("lang") or "sr"
    log.info("Repair cluster row cluster_id=%s lang=%s table=%s", cluster_id, lang, table_name)

    if dry_run:
        return True

    if table_name == "cluster_summaries":
        db.execute(
            """
            UPDATE cluster_summaries
            SET summary = %s, generated_article = %s, synthetic_headline = %s, synthetic_standfirst = %s
            WHERE cluster_id = %s AND lang = %s
            """,
            (new_summary, new_article, new_headline, new_standfirst, cluster_id, lang),
            fetch=False,
        )
    elif table_name == "cluster_summary_history":
        db.execute(
            """
            UPDATE cluster_summary_history
            SET summary = %s, generated_article = %s, synthetic_headline = %s, synthetic_standfirst = %s
            WHERE cluster_id = %s AND lang = %s AND created_at = %s
            """,
            (new_summary, new_article, new_headline, new_standfirst, cluster_id, lang, row.get("created_at")),
            fetch=False,
        )
    return True


def repair_table(table_name: str, *, dry_run: bool = False, limit: int | None = None) -> int:
    log.info("Scanning table '%s' for leaked JSON records...", table_name)

    if table_name == "articles":
        sql = """
            SELECT id, summary, description
            FROM articles
            WHERE (
                summary LIKE '{%'
                OR description LIKE '{%'
                OR summary LIKE '%"summary"%'
                OR description LIKE '%"summary"%'
            )
            ORDER BY id
        """
    else:
        sql = f"SELECT * FROM {table_name} ORDER BY cluster_id, lang, created_at"

    rows = db.execute(sql)
    if limit is not None:
        rows = rows[:limit]

    log.info("Checking %s candidate rows in '%s'.", len(rows), table_name)

    repaired_count = 0
    for row in rows:
        if table_name == "articles":
            if _repair_article_row(row, dry_run=dry_run):
                repaired_count += 1
            continue

        if _repair_cluster_row(row, table_name, dry_run=dry_run):
            repaired_count += 1

    action = "Would repair" if dry_run else "Repaired"
    log.info("%s %s rows in '%s'.", action, repaired_count, table_name)
    return repaired_count


def _repair_article_row(row: dict, *, dry_run: bool) -> bool:
    article_id = row.get("id")
    summary = row.get("summary") or ""
    description = row.get("description") or ""

    new_summary = summary
    new_description = description
    changed = False

    if _looks_like_jsonish_text_field(summary):
        cleaned = extract_clean_summary_text(summary)
        if cleaned and cleaned != summary:
            new_summary = cleaned
            changed = True

    if _looks_like_jsonish_text_field(description):
        cleaned = extract_clean_summary_text(description)
        if cleaned and cleaned != description:
            new_description = cleaned
            changed = True

    if not changed:
        return False

    log.info("Repair article id=%s", article_id)
    if dry_run:
        return True

    db.execute(
        """
        UPDATE articles
        SET summary = %s, description = %s
        WHERE id = %s
        """,
        (new_summary, new_description, article_id),
        fetch=False,
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--table",
        choices=("articles", "cluster_summaries", "cluster_summary_history", "all"),
        default="all",
        help="Which table(s) to repair (default: all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report rows that would be repaired without writing to the database.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on scanned rows per table.",
    )
    args = parser.parse_args()

    tables = ["articles", "cluster_summaries", "cluster_summary_history"] if args.table == "all" else [args.table]

    total = 0
    for table_name in tables:
        total += repair_table(table_name, dry_run=args.dry_run, limit=args.limit)

    mode = "dry-run" if args.dry_run else "write"
    log.info("Database repair complete (%s). Total affected rows: %s", mode, total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
