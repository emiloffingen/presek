import datetime
import json

from utils import redis_client


def main():
    bucket = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    key = f"presek:runtime_events:{bucket}"
    data = redis_client.hgetall(key) or {}

    filtered = {
        field: int(count)
        for field, count in sorted(data.items())
        if field.startswith(
            ("summary_path", "translation_path", "synthesis_path", "synthesis_db_persisted", "chat_path")
        )
    }
    reasons = {}
    synthesis_events = 0
    db_persisted_events = 0
    for field, count in filtered.items():
        if field.startswith("synthesis_path|"):
            synthesis_events += int(count)
            if "reason=" in field:
                for part in field.split("|"):
                    if part.startswith("reason="):
                        reason = part.split("=", 1)[1]
                        reasons[reason] = reasons.get(reason, 0) + int(count)
                        break
        if field.startswith("synthesis_db_persisted|"):
            db_persisted_events += int(count)

    print(
        json.dumps(
            {
                "bucket": bucket,
                "counts": filtered,
                "fallback_reasons": reasons,
                "synthesis_events": synthesis_events,
                "db_persisted_events": db_persisted_events,
                "persist_gap": max(0, synthesis_events - db_persisted_events),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
