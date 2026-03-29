import logging
import json
import os
from database import load_env
load_env()
from ai_engine import _call_cloudflare_ai
from prompts import ENTITY_EXTRACTION_PROMPT

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek")

print("Starting Cloudflare AI test...")
res = _call_cloudflare_ai('Title: Христијан Мицкоски', ENTITY_EXTRACTION_PROMPT)
print(f"Result: {res}")
