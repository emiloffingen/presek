import logging
import asyncio
import re
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional, Any, Dict
from collections import defaultdict
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse

from database import db_manager as db
from utils import (
    cached_response, set_cache, score_cluster, rank_articles_in_cluster,
    calculate_reading_time, is_balanced, build_editor_analytics_payload,
    redis_client,
    build_source_reputation_rows
)
from health import get_source_statuses, reset_source_policy
from config import BREAKING_SCORE_THRESHOLD, SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY, API_MAX_Q_LEN
from .common import _source_admin_authorized, _error_json
from .security import validate_date, validate_string_param, validate_email

log = logging.getLogger("presek")
router = APIRouter()
