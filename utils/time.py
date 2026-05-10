import datetime
import json
import re
from typing import Optional
import logging

log = logging.getLogger("presek")

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle datetime objects."""

    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            if isinstance(obj, datetime.datetime) and obj.tzinfo is None:
                return obj.isoformat() + "Z"
            return obj.isoformat()
        return super().default(obj)

def _coerce_datetime(value) -> Optional[datetime.datetime]:
    if isinstance(value, datetime.datetime):
        if value.tzinfo:
            return value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return value
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(value).replace(" ", "T"))
        if dt.tzinfo:
            return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except Exception as e:
        log.debug(f"Failed to parse datetime: {e}")
        m = re.match(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", str(value))
        if m:
            return datetime.datetime.fromisoformat(m.group(1).replace(" ", "T"))
    return None
