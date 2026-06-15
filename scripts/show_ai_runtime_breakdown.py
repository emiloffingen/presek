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
        if field.startswith(("summary_path", "translation_path", "synthesis_path", "chat_path"))
    }
    reasons = {}
    for field, count in filtered.items():
        if field.startswith("synthesis_path|") and "reason=" in field:
            for part in field.split("|"):
                if part.startswith("reason="):
                    reason = part.split("=", 1)[1]
                    reasons[reason] = reasons.get(reason, 0) + int(count)
                    break

    print(
        json.dumps(
            {"bucket": bucket, "counts": filtered, "fallback_reasons": reasons},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
