import logging
import json
import re
from core.database import db_manager as db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("repair_leaked_json")

def _looks_like_leaked_json_fragment(text: str) -> bool:
    clean = str(text or "").strip()
    if not clean:
        return False
    lowered = clean.lower()
    json_markers = (
        '"synthetic_headline"',
        '"synthetic_standfirst"',
        '"summary"',
        '"generated_article"',
        '"key_facts"',
        '"perspectives"',
        "verification_report",
    )
    marker_count = sum(1 for marker in json_markers if marker in lowered)
    bullet_json_lines = sum(1 for line in clean.splitlines() if line.strip().startswith(("• {", "• \"", "{", "\"")))
    return marker_count >= 2 or bullet_json_lines >= 2


def _clean_leaked_json_string(text: str) -> dict:
    data = {}
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
            for k in ["synthetic_headline", "synthetic_standfirst", "summary", "generated_article", "key_facts"]:
                if k in parsed:
                    data[k] = parsed[k]
    except Exception:
        # Fall back to regex extraction for truncated/broken JSON
        headline_match = re.search(r'"synthetic_headline"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_lines)
        if headline_match:
            try:
                data["synthetic_headline"] = headline_match.group(1).encode('utf-8').decode('unicode-escape', errors='ignore')
            except Exception:
                data["synthetic_headline"] = headline_match.group(1)
        
        standfirst_match = re.search(r'"synthetic_standfirst"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_lines)
        if standfirst_match:
            try:
                data["synthetic_standfirst"] = standfirst_match.group(1).encode('utf-8').decode('unicode-escape', errors='ignore')
            except Exception:
                data["synthetic_standfirst"] = standfirst_match.group(1)
            
        article_match = re.search(r'"generated_article"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_lines)
        if article_match:
            try:
                data["generated_article"] = article_match.group(1).encode('utf-8').decode('unicode-escape', errors='ignore')
            except Exception:
                data["generated_article"] = article_match.group(1)
            
        summary_array_match = re.search(r'"summary"\s*:\s*\[(.*?)\]', clean_lines, re.DOTALL)
        if summary_array_match:
            array_content = summary_array_match.group(1)
            bullet_matches = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', array_content)
            bullets = []
            for b in bullet_matches:
                try:
                    bullets.append(b.encode('utf-8').decode('unicode-escape', errors='ignore'))
                except Exception:
                    bullets.append(b)
            if bullets:
                data["summary"] = bullets

    for k in data:
        if isinstance(data[k], str):
            data[k] = data[k].replace('\\"', '"').replace('\\n', '\n').strip()
        elif isinstance(data[k], list):
            data[k] = [str(item).replace('\\"', '"').replace('\\n', '\n').strip() for item in data[k]]
            
    return data


def repair_table(table_name: str):
    log.info(f"Scanning table '{table_name}' for leaked JSON records...")
    
    # Select target rows
    rows = db.execute(f"SELECT * FROM {table_name}")
    log.info(f"Found {len(rows)} total rows in '{table_name}'. Checking each for JSON leaks...")
    
    repaired_count = 0
    for row in rows:
        summary_text = row.get("summary") or ""
        generated_article = row.get("generated_article") or ""
        
        # Check if either field looks like leaked JSON
        summary_leaked = _looks_like_leaked_json_fragment(summary_text)
        article_leaked = _looks_like_leaked_json_fragment(generated_article)
        
        if not (summary_leaked or article_leaked):
            continue
            
        log.info(f"Found leaked JSON in row: cluster_id={row.get('cluster_id')}, lang={row.get('lang') or 'sr'}")
        
        # Unpack clean data
        leaked_data = {}
        if summary_leaked:
            leaked_data = _clean_leaked_json_string(summary_text)
        else:
            leaked_data = _clean_leaked_json_string(generated_article)
            
        if not leaked_data:
            log.warning(f"Could not extract clean data from JSON fragment in row: cluster_id={row.get('cluster_id')}")
            continue
            
        # Get existing values
        headline = row.get("synthetic_headline") or ""
        standfirst = row.get("synthetic_standfirst") or ""
        
        # Patch them
        new_headline = leaked_data.get("synthetic_headline") or headline
        new_standfirst = leaked_data.get("synthetic_standfirst") or standfirst
        new_article = leaked_data.get("generated_article") or row.get("generated_article")
        
        new_summary = summary_text
        if "summary" in leaked_data:
            if isinstance(leaked_data["summary"], list):
                new_summary = "\n".join(f"• {b}" for b in leaked_data["summary"])
            else:
                new_summary = str(leaked_data["summary"])
                
        # Perform db update
        cluster_id = row.get("cluster_id")
        lang = row.get("lang") or "sr"
        
        if table_name == "cluster_summaries":
            db.execute(
                """
                UPDATE cluster_summaries
                SET summary = %s, generated_article = %s, synthetic_headline = %s, synthetic_standfirst = %s
                WHERE cluster_id = %s AND lang = %s
                """,
                (new_summary, new_article, new_headline, new_standfirst, cluster_id, lang),
                fetch=False
            )
        elif table_name == "cluster_summary_history":
            created_at = row.get("created_at")
            db.execute(
                """
                UPDATE cluster_summary_history
                SET summary = %s, generated_article = %s, synthetic_headline = %s, synthetic_standfirst = %s
                WHERE cluster_id = %s AND lang = %s AND created_at = %s
                """,
                (new_summary, new_article, new_headline, new_standfirst, cluster_id, lang, created_at),
                fetch=False
            )
            
        repaired_count += 1
        log.info(f"Successfully repaired row: cluster_id={cluster_id}, lang={lang}")

    log.info(f"Completed table '{table_name}'. Total repaired rows: {repaired_count}")


if __name__ == "__main__":
    repair_table("cluster_summaries")
    repair_table("cluster_summary_history")
    log.info("Database repair complete!")
