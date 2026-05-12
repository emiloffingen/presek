import json
from database import db_manager

def get_metadata(key: str, default=None):
    res = db_manager.execute('SELECT value FROM system_metadata WHERE key = %s', (key,))
    if res:
        val = res[0]['value']
        # psycopg may already decode JSONB columns to Python lists/dicts
        if isinstance(val, (dict, list)):
            return val
        return json.loads(val)
    return default
