#!/usr/bin/env python3
"""Presek shared-memory MCP client over the Shield's HTTP relay (stdio server).

For agents on hosts WITHOUT the presek repo or database credentials (e.g. a
tablet running opencode + deepseek). This is a pure-stdlib stdio MCP server: it
exposes the same shared-memory tools, but every call is forwarded to the
Tailscale relay (see mcp/shared_memory_relay.py), which holds the DB access.

No third-party dependency (uses urllib). No database credentials here.

Config (env):
    SHARED_MEMORY_RELAY_URL   e.g. http://100.77.135.12:8790/mcp
    SHARED_MEMORY_TOKEN       bearer token (matches the relay)
    PRESEK_AGENT_ID           e.g. tablet   (attributes writes)

stdout is a strict JSON-RPC stream; logs go to stderr.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = {"2025-06-18", "2025-03-26", "2024-11-05"}
SERVER_NAME = "presek-shared-memory-relay"
SERVER_VERSION = "1.0.0"


def log(msg: str) -> None:
    sys.stderr.write(f"[shared-memory-client] {msg}\n")
    sys.stderr.flush()


def _relay_url() -> str:
    url = os.environ.get("SHARED_MEMORY_RELAY_URL", "").strip()
    if not url:
        raise RuntimeError("SHARED_MEMORY_RELAY_URL is not set")
    return url


def _token() -> str:
    tok = os.environ.get("SHARED_MEMORY_TOKEN", "").strip()
    if not tok:
        raise RuntimeError("SHARED_MEMORY_TOKEN is not set")
    return tok


def _call_relay(msg: dict) -> dict:
    data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        _relay_url(),
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_token()}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"relay HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"relay unreachable: {type(exc).__name__}: {exc}") from exc
    if not body:
        return {}
    return json.loads(body)


def handle_request(msg: dict) -> dict | None:
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    # Local handshake so the client works even if the relay is briefly down.
    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Shared Presek memory via the Shield relay. Same tools as the "
                    "direct server: memory_*, task_*, fact_*. Writes are attributed "
                    "to PRESEK_AGENT_ID."
                ),
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    # Forward everything else (tools/list, tools/call, prompts/*, resources/*).
    # Inject this agent's identity so writes are attributed correctly on the
    # relay side (the relay's own env is generic).
    forwarded = dict(msg)
    if method == "tools/call":
        args = dict(params.get("arguments") or {})
        agent_id = os.environ.get("PRESEK_AGENT_ID", "").strip()
        if agent_id and not args.get("agent_id"):
            args["agent_id"] = agent_id
        forwarded["params"] = {**params, "arguments": args}
    else:
        forwarded["params"] = params
    try:
        return _call_relay(forwarded)
    except Exception as exc:
        if req_id is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps({"error": str(exc)})}],
                "isError": True,
            },
        }


def main() -> None:
    log(
        f"start (relay={os.environ.get('SHARED_MEMORY_RELAY_URL', 'UNSET')}, agent={os.environ.get('PRESEK_AGENT_ID', 'unknown')})"
    )
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
        except Exception as exc:
            log(f"handler crashed: {exc}")
            response = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": str(exc)}}
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
