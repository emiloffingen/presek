import logging
import json
import os
from database import _load_env
_load_env()
from ai_engine import _call_ai
from prompts import ENTITY_EXTRACTION_PROMPT

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek")

print("Starting AI test...")
res, provider = _call_ai('Title: Христијан Мицкоски најави нови инвестиции', ENTITY_EXTRACTION_PROMPT, json_mode=True)
print(f"Provider: {provider}, Result: {res}")
