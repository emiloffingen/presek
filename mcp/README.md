# Presek MCP servers

Local, dependency-free (Python stdlib) Model Context Protocol servers used by the
opencode agents. Both speak newline-delimited JSON-RPC 2.0 over **stdio**; all
diagnostics go to **stderr** so stdout stays a valid JSON-RPC stream.

## `presek_mcp.py` — ops
Read-only operational access to the running Presek stack.

| Tool | Purpose |
| --- | --- |
| `presek_health` | `/api/health` (db, redis, queues) + AI quota |
| `presek_ops_snapshot` | combined queues/freshness/synthesis snapshot |
| `presek_queue_status` | Celery queue depths |
| `presek_recent_logs` | tail a whitelisted service log (optional regex) |
| `presek_db_query` | read-only SQL (SELECT/WITH/SHOW/EXPLAIN only) |
| `presek_ai_quota` | per-provider daily AI budgets |
| `presek_version` | backend version |

## `shared_memory_mcp.py` — cross-agent shared memory
Durable memory that every agent on every host shares, backed by the same Neon
Postgres the stack uses (not Redis — that is the Celery broker).

| Tool | Purpose |
| --- | --- |
| `memory_write` / `memory_search` / `memory_recent` / `memory_get` | notes, decisions, handoffs, context |
| `task_add` / `task_list` / `task_claim` / `task_update` | shared work queue with atomic leases |
| `fact_set` / `fact_get` | namespaced key/value scratchpad |
| `memory_stats` | counts for a namespace |

Set `PRESEK_SHARED_MEMORY=0` for read-only mode. Set `PRESEK_AGENT_ID` to
attribute writes to a given agent.

## Manual smoke test
```sh
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 mcp/presek_mcp.py
```
