import json
import logging
import urllib.request
import urllib.error
from config import CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, CLOUDFLARE_KV_NAMESPACE_ID

log = logging.getLogger("presek.kv")

BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/storage/kv/namespaces/{CLOUDFLARE_KV_NAMESPACE_ID}/values"

def put_kv(key: str, value: any, ttl: int = 3600):
    """Write a value to Cloudflare KV. Value will be JSON encoded if it's not a string."""
    if not CLOUDFLARE_API_TOKEN or not CLOUDFLARE_KV_NAMESPACE_ID:
        return False
    
    if not isinstance(value, str):
        value = json.dumps(value)
    
    url = f"{BASE_URL}/{key}"
    if ttl:
        url += f"?expiration_ttl={ttl}"
        
    try:
        req = urllib.request.Request(
            url,
            data=value.encode("utf-8"),
            headers={
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
                "Content-Type": "text/plain"
            },
            method="PUT"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("success"):
                log.warning(f"[kv] API error: {data.get('errors')}")
            return data.get("success", False)
    except urllib.error.HTTPError as e:
        raw_err = e.read().decode("utf-8")
        log.warning(f"[kv] PUT failed for {key}: {e.code} {e.reason} - {raw_err}")
        return False
    except Exception as e:
        log.warning(f"[kv] PUT failed for {key}: {e}")
        return False

def get_kv(key: str, is_json: bool = True):
    """Read a value from Cloudflare KV."""
    if not CLOUDFLARE_API_TOKEN or not CLOUDFLARE_KV_NAMESPACE_ID:
        return None
        
    url = f"{BASE_URL}/{key}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            val = resp.read().decode("utf-8")
            if is_json:
                try:
                    return json.loads(val)
                except:
                    return val
            return val
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None # Cache miss
        log.warning(f"[kv] GET failed for {key}: {e}")
        return None
    except Exception as e:
        log.warning(f"[kv] GET failed for {key}: {e}")
        return None
