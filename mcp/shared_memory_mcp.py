#!/usr/bin/env python3
"""Presek shared-memory MCP server (stdio, stdio-only, dependency-free).

Gives multiple agents (opencode instances across the Shield/phone/any host) one
shared, durable memory backed by the Neon Postgres database the whole stack
already shares. No extra service, no Redis (Redis is the Celery broker, so it is
NOT safe to share).

Stores notes (free-form memory), tasks (shared work queue with leases), and
facts (key/value scratchpad). Every row is namespaced and attributed so agents
can coordinate without clobbering each other.

stdout is a strict JSON-RPC stream; all diagnostics go to stderr.

Run:  python3 mcp/shared_memory_mcp.py     (cwd must be the presek root)
Env:  PRESEK_SHARED_MEMORY=0 disables writes (read-only mode).
"""

from __future__ import annotations

import datetime
import json
import os
import sys

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = {"2025-06-18", "2025-03-26", "2024-11-05"}
SERVER_NAME = "presek-shared-memory"
SERVER_VERSION = "1.0.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_NS = "default"

VALID_KINDS = {"note", "decision", "handoff", "context"}
VALID_STATUS = {"open", "in_progress", "blocked", "done", "cancelled"}
MAX_BODY = 20000
MAX_RETURN = 200

_DDL = """
CREATE TABLE IF NOT EXISTS agent_memory (
    id            BIGSERIAL PRIMARY KEY,
    namespace     TEXT NOT NULL DEFAULT 'default',
    agent_id      TEXT NOT NULL DEFAULT 'unknown',
    kind          TEXT NOT NULL DEFAULT 'note',
    title         TEXT,
    body          TEXT NOT NULL,
    tags          TEXT[] NOT NULL DEFAULT '{}',
    meta          JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_host   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS agent_memory_ns_created_idx ON agent_memory (namespace, created_at DESC);
CREATE INDEX IF NOT EXISTS agent_memory_tags_idx ON agent_memory USING GIN (tags);

CREATE TABLE IF NOT EXISTS agent_tasks (
    id            BIGSERIAL PRIMARY KEY,
    namespace     TEXT NOT NULL DEFAULT 'default',
    title         TEXT NOT NULL,
    detail        TEXT,
    status        TEXT NOT NULL DEFAULT 'open',
    priority      INTEGER NOT NULL DEFAULT 3,
    assigned_to   TEXT,
    lease_until   TIMESTAMPTZ,
    created_by    TEXT,
    result        TEXT,
    meta          JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_host   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS agent_tasks_ns_status_idx ON agent_tasks (namespace, status, priority);

CREATE TABLE IF NOT EXISTS agent_facts (
    namespace     TEXT NOT NULL DEFAULT 'default',
    key           TEXT NOT NULL,
    value         TEXT NOT NULL,
    agent_id      TEXT,
    source_host   TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (namespace, key)
);
"""

_TABLE_READY = False


def log(msg: str) -> None:
    sys.stderr.write(f"[shared-memory-mcp] {msg}\n")
    sys.stderr.flush()


def writes_enabled() -> bool:
    return os.environ.get("PRESEK_SHARED_MEMORY", "1").strip().lower() not in ("0", "false", "off", "no")


def _bootstrap() -> None:
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        for raw in open(env_path, encoding="utf-8"):
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _db():
    _bootstrap()
    global _TABLE_READY
    from core.database import db_manager

    if not _TABLE_READY:
        db_manager.execute(_DDL, fetch=False, read_only=False)
        _TABLE_READY = True
    return db_manager


def _ns(args: dict) -> str:
    return str(args.get("namespace") or DEFAULT_NS).strip()[:120] or DEFAULT_NS


def _agent(args: dict) -> str:
    return str(args.get("agent_id") or os.environ.get("PRESEK_AGENT_ID") or "unknown").strip()[:120]


def _host() -> str:
    import socket

    try:
        return socket.gethostname()[:120]
    except Exception:
        return "unknown"


def _clamp(value, low, high):
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return low


def _require_write() -> dict | None:
    if writes_enabled():
        return None
    return {"error": "shared memory is read-only (PRESEK_SHARED_MEMORY=0)"}


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------


def mem_write(args: dict) -> dict:
    blocked = _require_write()
    if blocked:
        return blocked
    body = str(args.get("body") or "").strip()
    if not body:
        return {"error": "body is required"}
    kind = str(args.get("kind") or "note").strip().lower()
    if kind not in VALID_KINDS:
        return {"error": f"kind must be one of {sorted(VALID_KINDS)}"}
    db = _db()
    rows = db.execute(
        """
        INSERT INTO agent_memory (namespace, agent_id, kind, title, body, tags, meta, source_host)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (
            _ns(args),
            _agent(args),
            kind,
            (str(args.get("title"))[:300] if args.get("title") else None),
            body[:MAX_BODY],
            list(args.get("tags") or []),
            json.dumps(args.get("meta") or {}),
            _host(),
        ),
        read_only=False,
    )
    row = rows[0] if rows else {}
    return {"ok": True, "id": row.get("id"), "created_at": str(row.get("created_at"))}


def mem_search(args: dict) -> dict:
    query = str(args.get("query") or "").strip()
    limit = _clamp(args.get("limit", 20), 1, MAX_RETURN)
    tags = list(args.get("tags") or [])
    kind = args.get("kind")
    db = _db()
    sql = "SELECT id, namespace, agent_id, kind, title, body, tags, source_host, created_at"
    sql += " FROM agent_memory WHERE namespace = %s"
    params: list = [_ns(args)]
    if query:
        sql += " AND (title ILIKE %s OR body ILIKE %s)"
        like = f"%{query}%"
        params += [like, like]
    if tags:
        sql += " AND tags && %s"
        params.append(tags)
    if kind:
        sql += " AND kind = %s"
        params.append(kind)
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(str(limit))
    rows = db.execute(sql, tuple(params), read_only=True)
    return {"count": len(rows or []), "memories": rows or []}


def mem_recent(args: dict) -> dict:
    limit = _clamp(args.get("limit", 20), 1, MAX_RETURN)
    db = _db()
    rows = db.execute(
        """
        SELECT id, agent_id, kind, title, body, tags, source_host, created_at
        FROM agent_memory WHERE namespace = %s
        ORDER BY created_at DESC LIMIT %s
        """,
        (_ns(args), str(limit)),
        read_only=True,
    )
    return {"count": len(rows or []), "memories": rows or []}


def mem_get(args: dict) -> dict:
    mem_id = _clamp(args.get("id", 0), 0, 2**62)
    if not mem_id:
        return {"error": "id is required"}
    db = _db()
    rows = db.execute("SELECT * FROM agent_memory WHERE id = %s", (mem_id,), read_only=True)
    if not rows:
        return {"error": f"memory {mem_id} not found"}
    return {"memory": rows[0]}


def task_add(args: dict) -> dict:
    blocked = _require_write()
    if blocked:
        return blocked
    title = str(args.get("title") or "").strip()
    if not title:
        return {"error": "title is required"}
    db = _db()
    rows = db.execute(
        """
        INSERT INTO agent_tasks (namespace, title, detail, status, priority, created_by, meta, source_host)
        VALUES (%s, %s, %s, 'open', %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (
            _ns(args),
            title[:300],
            (str(args.get("detail"))[:MAX_BODY] if args.get("detail") else None),
            _clamp(args.get("priority", 3), 1, 5),
            _agent(args),
            json.dumps(args.get("meta") or {}),
            _host(),
        ),
        read_only=False,
    )
    row = rows[0] if rows else {}
    return {"ok": True, "id": row.get("id"), "created_at": str(row.get("created_at"))}


def task_list(args: dict) -> dict:
    status = args.get("status")
    limit = _clamp(args.get("limit", 50), 1, MAX_RETURN)
    db = _db()
    sql = "SELECT * FROM agent_tasks WHERE namespace = %s"
    params: list = [_ns(args)]
    if status:
        sql += " AND status = %s"
        params.append(status)
    sql += " ORDER BY priority ASC, created_at ASC LIMIT %s"
    params.append(str(limit))
    rows = db.execute(sql, tuple(params), read_only=True)
    return {"count": len(rows or []), "tasks": rows or []}


def task_claim(args: dict) -> dict:
    """Atomically claim a task for this agent (lease) or a specific task id."""
    blocked = _require_write()
    if blocked:
        return blocked
    lease_minutes = _clamp(args.get("lease_minutes", 30), 1, 1440)
    db = _db()
    who = _agent(args)
    params: list = [_ns(args), who, f"{lease_minutes} minutes"]
    sql = """
        UPDATE agent_tasks
        SET status = 'in_progress', assigned_to = %s, lease_until = NOW() + %s::interval, updated_at = NOW()
        WHERE id = (
            SELECT id FROM agent_tasks
            WHERE namespace = %s
              AND (status = 'open' OR (status = 'in_progress' AND lease_until IS NOT NULL AND lease_until < NOW()))
    """
    params2: list = [who, f"{lease_minutes} minutes", _ns(args)]
    if args.get("id"):
        sql += " AND id = %s"
        params2.append(_clamp(args["id"], 0, 2**62))
    sql += " ORDER BY priority ASC, created_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED)"
    sql += " RETURNING id, title, detail, priority, status, lease_until"
    rows = db.execute(sql, tuple(params2), read_only=False)
    if not rows:
        return {"ok": False, "reason": "no claimable task"}
    return {"ok": True, "task": rows[0]}


def task_update(args: dict) -> dict:
    blocked = _require_write()
    if blocked:
        return blocked
    task_id = _clamp(args.get("id", 0), 0, 2**62)
    if not task_id:
        return {"error": "id is required"}
    status = args.get("status")
    if status is not None and status not in VALID_STATUS:
        return {"error": f"status must be one of {sorted(VALID_STATUS)}"}
    sets, params = [], []
    if status is not None:
        sets.append("status = %s")
        params.append(status)
        if status in ("done", "cancelled"):
            sets.append("lease_until = NULL")
    if args.get("result") is not None:
        sets.append("result = %s")
        params.append(str(args["result"])[:MAX_BODY])
    if args.get("assigned_to") is not None:
        sets.append("assigned_to = %s")
        params.append(str(args["assigned_to"])[:120])
    if args.get("detail") is not None:
        sets.append("detail = %s")
        params.append(str(args["detail"])[:MAX_BODY])
    if not sets:
        return {"error": "nothing to update"}
    sets.append("updated_at = NOW()")
    db = _db()
    params += [_ns(args), task_id]
    rows = db.execute(
        f"UPDATE agent_tasks SET {', '.join(sets)} WHERE namespace = %s AND id = %s RETURNING *",
        tuple(params),
        read_only=False,
    )
    if not rows:
        return {"error": f"task {task_id} not found in namespace {_ns(args)}"}
    return {"ok": True, "task": rows[0]}


def fact_set(args: dict) -> dict:
    blocked = _require_write()
    if blocked:
        return blocked
    key = str(args.get("key") or "").strip()
    if not key:
        return {"error": "key is required"}
    value = str(args.get("value") or "")
    db = _db()
    db.execute(
        """
        INSERT INTO agent_facts (namespace, key, value, agent_id, source_host, updated_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (namespace, key)
        DO UPDATE SET value = EXCLUDED.value, agent_id = EXCLUDED.agent_id,
                      source_host = EXCLUDED.source_host, updated_at = NOW()
        """,
        (_ns(args), key[:200], value[:MAX_BODY], _agent(args), _host()),
        read_only=False,
    )
    return {"ok": True, "key": key}


def fact_get(args: dict) -> dict:
    key = str(args.get("key") or "").strip()
    db = _db()
    if key:
        rows = db.execute(
            "SELECT * FROM agent_facts WHERE namespace = %s AND key = %s",
            (_ns(args), key),
            read_only=True,
        )
        if not rows:
            return {"error": f"fact '{key}' not found"}
        return {"fact": rows[0]}
    rows = db.execute(
        "SELECT * FROM agent_facts WHERE namespace = %s ORDER BY key LIMIT 200",
        (_ns(args),),
        read_only=True,
    )
    return {"count": len(rows or []), "facts": rows or []}


def memory_stats(args: dict) -> dict:
    db = _db()
    ns = _ns(args)
    row = db.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM agent_memory WHERE namespace = %s) AS memories,
          (SELECT COUNT(*) FROM agent_tasks  WHERE namespace = %s) AS tasks,
          (SELECT COUNT(*) FROM agent_facts  WHERE namespace = %s) AS facts,
          (SELECT COUNT(*) FROM agent_tasks  WHERE namespace = %s AND status IN ('open','in_progress','blocked')) AS tasks_open,
          (SELECT MAX(created_at) FROM agent_memory WHERE namespace = %s) AS last_memory_at
        """,
        (ns, ns, ns, ns, ns),
        read_only=True,
    )
    return {"namespace": ns, "stats": (row[0] if row else {})}


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

TOOLS: dict[str, dict] = {
    "memory_write": {
        "description": "Append a durable shared memory (note/decision/handoff/context) visible to every agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": DEFAULT_NS},
                "agent_id": {"type": "string"},
                "kind": {"type": "string", "enum": sorted(VALID_KINDS), "default": "note"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "meta": {"type": "object"},
            },
            "required": ["body"],
            "additionalProperties": False,
        },
        "handler": mem_write,
    },
    "memory_search": {
        "description": "Full-text search shared memories by query text and/or tags within a namespace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": DEFAULT_NS},
                "query": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "kind": {"type": "string", "enum": sorted(VALID_KINDS)},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RETURN, "default": 20},
            },
            "additionalProperties": False,
        },
        "handler": mem_search,
    },
    "memory_recent": {
        "description": "Most recent shared memories in a namespace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": DEFAULT_NS},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RETURN, "default": 20},
            },
            "additionalProperties": False,
        },
        "handler": mem_recent,
    },
    "memory_get": {
        "description": "Fetch one shared memory by id.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        },
        "handler": mem_get,
    },
    "task_add": {
        "description": "Add a shared task for any agent to pick up.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": DEFAULT_NS},
                "agent_id": {"type": "string"},
                "title": {"type": "string"},
                "detail": {"type": "string"},
                "priority": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
                "meta": {"type": "object"},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        "handler": task_add,
    },
    "task_list": {
        "description": "List shared tasks (optionally by status).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": DEFAULT_NS},
                "status": {"type": "string", "enum": sorted(VALID_STATUS)},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RETURN, "default": 50},
            },
            "additionalProperties": False,
        },
        "handler": task_list,
    },
    "task_claim": {
        "description": "Atomically claim the next open/unleased shared task (lease), or a specific id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": DEFAULT_NS},
                "agent_id": {"type": "string"},
                "id": {"type": "integer"},
                "lease_minutes": {"type": "integer", "minimum": 1, "maximum": 1440, "default": 30},
            },
            "additionalProperties": False,
        },
        "handler": task_claim,
    },
    "task_update": {
        "description": "Update a shared task: status, result, assignee or detail.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": DEFAULT_NS},
                "id": {"type": "integer"},
                "status": {"type": "string", "enum": sorted(VALID_STATUS)},
                "result": {"type": "string"},
                "assigned_to": {"type": "string"},
                "detail": {"type": "string"},
            },
            "required": ["id"],
            "additionalProperties": False,
        },
        "handler": task_update,
    },
    "fact_set": {
        "description": "Set a namespaced key/value fact shared across agents (upsert).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": DEFAULT_NS},
                "key": {"type": "string"},
                "value": {"type": "string"},
                "agent_id": {"type": "string"},
            },
            "required": ["key", "value"],
            "additionalProperties": False,
        },
        "handler": fact_set,
    },
    "fact_get": {
        "description": "Get one shared fact by key, or list all facts in the namespace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": DEFAULT_NS},
                "key": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "handler": fact_get,
    },
    "memory_stats": {
        "description": "Counts of memories/tasks/facts and the freshest memory time for a namespace.",
        "inputSchema": {
            "type": "object",
            "properties": {"namespace": {"type": "string", "default": DEFAULT_NS}},
            "additionalProperties": False,
        },
        "handler": memory_stats,
    },
}


# --------------------------------------------------------------------------
# JSON-RPC
# --------------------------------------------------------------------------


def _ok(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_request(msg: dict):
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        return _ok(
            req_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Shared, durable memory for the Presek project, backed by Postgres and "
                    "visible to every agent on every host. Use memory_write/memory_search to "
                    "coordinate, task_* for the shared work queue, and fact_* for small "
                    "key/value state."
                ),
            },
        )

    if method == "ping":
        return _ok(req_id, {})

    if method == "tools/list":
        return _ok(
            req_id,
            {
                "tools": [
                    {"name": n, "description": s["description"], "inputSchema": s["inputSchema"]}
                    for n, s in TOOLS.items()
                ]
            },
        )

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        spec = TOOLS.get(name)
        if spec is None:
            return _ok(req_id, {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True})
        try:
            payload = spec["handler"](args)
            is_error = isinstance(payload, dict) and "error" in payload and len(payload) == 1
            text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        except Exception as exc:
            text = json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
            is_error = True
        return _ok(req_id, {"content": [{"type": "text", "text": text}], "isError": is_error})

    if method in ("prompts/list",):
        return _ok(req_id, {"prompts": []})
    if method in ("resources/list",):
        return _ok(req_id, {"resources": []})
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    return _err(req_id, -32601, f"Method not found: {method}")


def main() -> None:
    log(f"start (root={ROOT}, pid={os.getpid()}, writes={'on' if writes_enabled() else 'OFF'})")
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as exc:
            log(f"invalid JSON: {exc}")
            continue
        try:
            response = handle_request(msg)
        except Exception as exc:  # pragma: no cover
            log(f"handler crashed: {exc}")
            response = _err(msg.get("id"), -32603, f"Internal error: {exc}")
        if response is None:
            continue
        try:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, default=str) + "\n")
            sys.stdout.flush()
        except (BrokenPipeError, ValueError):
            break
    log("stdin closed; exiting")


if __name__ == "__main__":
    main()
