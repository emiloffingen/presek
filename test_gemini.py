import logging
import json
import os
from database import load_env
load_env()
from ai_engine import _call_gemini
from prompts import ENTITY_EXTRACTION_PROMPT

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek")

print("Starting Gemini test...")
res = _call_gemini('Title: Христијан Мицкоски најави нови инвестиции', ENTITY_EXTRACTION_PROMPT, json_mode=True)
print(f"Result: {res}")
