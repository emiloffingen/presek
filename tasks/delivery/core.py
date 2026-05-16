import datetime
import json
import urllib.parse
import httpx

from core.database import db_manager as db
from core.config import NTFY_TOKEN
from tasks.utils import log, _PUBLIC_SITE_URL

_BREAKING_ALERT_QUEUE_DEPTH_LIMIT = 100
_BREAKING_ALERT_TASK_LOCK = "lock:breaking_alerts"
_BREAKING_ALERT_LOCK_TTL = 300

_LOCALIZED_DELIVERY = {
    "sr": {
        "title": "Presek personalizovani brifing",
        "followed_topics": "Pracene teme",
        "followed_sources": "Praceni izvori",
        "sources": "izvori",
        "reason_default": "važna razvojna linija",
        "important_story": "Važna priča",
        "difference": "Razlika",
        "open": "Otvoreno",
        "read_briefing": "Otvori brifing",
        "ntfy_title": "Presek · Jutarnji brifing",
    },
    "mk": {
        "title": "Пресек персонализиран брифинг",
        "followed_topics": "Следени теми",
        "followed_sources": "Следени извори",
        "sources": "извори",
        "reason_default": "важна развојна линија",
        "important_story": "Важна приказна",
        "difference": "Разлика",
        "open": "Отворено",
        "read_briefing": "Отвори го целосниот брифинг",
        "ntfy_title": "Пресек · Утрински брифинг",
    },
}

def _parse_row_datetime(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception as e:
            log.debug(f"Failed to parse datetime: {e}")
            return None
    return None

def _record_delivery_tracking_event(
    sync_token,
    event_type,
    delivery_kind,
    *,
    channel="ntfy",
    target="",
    cluster_id=None,
    parent_event_id=None,
    metadata=None,
):
    row = db.execute_one(
        """INSERT INTO delivery_tracking_events
           (sync_token, parent_event_id, event_type, delivery_kind, channel, target, cluster_id, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
           RETURNING id""",
        (
            sync_token,
            parent_event_id,
            str(event_type or "").strip(),
            str(delivery_kind or "").strip(),
            str(channel or "ntfy").strip() or "ntfy",
            str(target or "").strip(),
            str(cluster_id or "").strip() or None,
            json.dumps(metadata or {}),
        ),
    )
    return int((row or {}).get("id") or 0)

def _tracked_delivery_url(event_id, event_type, path):
    event_id = int(event_id or 0)
    clean_path = str(path or "").strip()
    if not clean_path.startswith("/"):
        clean_path = "/briefing"
    query = urllib.parse.urlencode({"event_id": event_id, "redirect": clean_path})
    return f"{_PUBLIC_SITE_URL}/api/delivery/track/{urllib.parse.quote(str(event_type or 'click'), safe='')}?{query}"

def _send_web_push_message(subscription_json_str, title, message, click_url=None):
    from core.config import VAPID_PRIVATE_KEY, VAPID_CLAIMS

    try:
        import pywebpush
        import json

        sub_info = json.loads(subscription_json_str)
        payload = json.dumps(
            {
                "title": str(title or "Presek")[:120],
                "message": str(message or "")[:500],
                "click_url": str(click_url or "")[:500],
            }
        )
        pywebpush.webpush(
            subscription_info=sub_info,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS,
            ttl=86400,
        )
        return True
    except Exception as e:
        log.warning(f"[tasks] web_push error: {e}")
        return False

def _send_ntfy_message(topic, title, message, tags="newspaper", click_url=None):
    clean_topic = str(topic or "").strip()
    import re

    clean_topic = re.sub(r"[^a-zA-Z0-9_-]", "", clean_topic)[:64]

    clean_message = str(message or "").strip()
    if not clean_topic or not clean_message:
        return False

    params = {
        "title": str(title or "Presek").strip()[:120],
        "tags": str(tags or "newspaper"),
        "priority": "default",
    }
    if click_url:
        params["click"] = str(click_url).strip()[:500]

    headers = {}
    if NTFY_TOKEN and NTFY_TOKEN != "YOUR_NTFY_TOKEN_HERE":
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"

    url = f"https://ntfy.sh/{urllib.parse.quote(clean_topic, safe='')}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                url,
                content=clean_message.encode("utf-8"),
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            return True
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        log.warning(f"[tasks] ntfy delivery failed for topic {clean_topic}: {e}")
        return False

def _normalize_alert_context(context):
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except Exception as e:
            log.debug(f"Failed to parse alert context JSON: {e}")
            return {}
    if not isinstance(context, dict):
        return {}
    clean = {}
    for key, value in context.items():
        key_text = str(key or "").strip()
        value_text = str(value or "").strip()
        if key_text and value_text:
            clean[key_text] = value_text
    return clean

def _next_alert_context(existing_context, candidate):
    context = _normalize_alert_context(existing_context)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for key in candidate["throttle_keys"]:
        context[key] = now
    return context

def _load_delivery_kind_performance(days=30):
    rows = db.execute(
        """SELECT delivery_kind, 
        COUNT(*) FILTER (WHERE event_type = 'send') AS sends, 
        COUNT(*) FILTER (WHERE event_type = 'open') AS opens, 
        COUNT(*) FILTER (WHERE event_type = 'click') AS clicks 
        FROM delivery_tracking_events 
        WHERE created_at >= NOW() - (%s * INTERVAL '1 day') 
        GROUP BY delivery_kind""",
        (days,),
    )
    performance = {}
    for row in rows or []:
        kind = str(row.get("delivery_kind") or "").strip()
        if not kind:
            continue
        sends = int(row.get("sends") or 0)
        opens = int(row.get("opens") or 0)
        clicks = int(row.get("clicks") or 0)
        performance[kind] = {
            "sends": sends,
            "opens": opens,
            "clicks": clicks,
            "open_rate": (opens / sends) if sends else 0.0,
            "click_rate": (clicks / sends) if sends else 0.0,
        }
    return performance

def _load_breaking_target_performance(days=45):
    send_rows = db.execute(
        """SELECT id, metadata 
        FROM delivery_tracking_events 
        WHERE delivery_kind = 'breaking' AND event_type = 'send' 
        AND created_at >= NOW() - (%s * INTERVAL '1 day')""",
        (days,),
    )
    child_rows = db.execute(
        """SELECT parent_event_id, event_type 
        FROM delivery_tracking_events 
        WHERE delivery_kind = 'breaking' AND event_type IN ('open', 'click') 
        AND created_at >= NOW() - (%s * INTERVAL '1 day')""",
        (days,),
    )

    child_map = {}
    for row in child_rows or []:
        parent_id = int(row.get("parent_event_id") or 0)
        if parent_id <= 0:
            continue
        bucket = child_map.setdefault(parent_id, {"opens": 0, "clicks": 0})
        event_type = str(row.get("event_type") or "").strip()
        if event_type == "open":
            bucket["opens"] += 1
        elif event_type == "click":
            bucket["clicks"] += 1

    topic_map = {}
    source_map = {}
    for row in send_rows or []:
        event_id = int(row.get("id") or 0)
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception as e:
                log.debug(f"Failed to parse metadata JSON: {e}")
                metadata = {}
        child_stats = child_map.get(event_id) or {"opens": 0, "clicks": 0}

        for topic in metadata.get("matched_topics") or []:
            clean = str(topic or "").strip()
            if not clean:
                continue
            bucket = topic_map.setdefault(clean, {"sends": 0, "opens": 0, "clicks": 0})
            bucket["sends"] += 1
            bucket["opens"] += child_stats["opens"]
            bucket["clicks"] += child_stats["clicks"]

        for source in metadata.get("matched_sources") or []:
            clean = str(source or "").strip()
            if not clean:
                continue
            bucket = source_map.setdefault(clean, {"sends": 0, "opens": 0, "clicks": 0})
            bucket["sends"] += 1
            bucket["opens"] += child_stats["opens"]
            bucket["clicks"] += child_stats["clicks"]

    for mapping in (topic_map, source_map):
        for _, bucket in mapping.items():
            sends = int(bucket.get("sends") or 0)
            opens = int(bucket.get("opens") or 0)
            clicks = int(bucket.get("clicks") or 0)
            bucket["open_rate"] = (opens / sends) if sends else 0.0
            bucket["click_rate"] = (clicks / sends) if sends else 0.0

    return {"topics": topic_map, "sources": source_map}
