# BRIEFING — 2026-06-29T13:15:00+02:00

## Mission
Orchestrate the development, testing, and verification of Interactive Stance Visualizations, CSP Telemetry endpoint, and Automated Backup Verification for Presek.

## 🔒 My Identity
- Archetype: teamwork_preview_orchestrator
- Roles: orchestrator, user_liaison, human_reporter, successor
- Working directory: /home/emiloffingen/presek/.agents/orchestrator
- Original parent: parent
- Original parent conversation ID: 7ccda073-6af2-494c-b1e9-ba73ad602283

## 🔒 My Workflow
- **Pattern**: Project
- **Scope document**: /home/emiloffingen/presek/PROJECT.md
1. **Decompose**: Decompose the project requirements (R1, R2, R3) into separate implementation milestones and an E2E testing track.
2. **Dispatch & Execute**:
   - **Delegate (sub-orchestrator)**: Spawn sub-orchestrators for major milestones and tracks.
3. **On failure** (in this order):
   - Retry: nudge stuck agent or re-send task
   - Replace: spawn fresh agent with partial progress
   - Skip: proceed without (only if non-critical)
   - Redistribute: split stuck agent's remaining work
   - Redesign: re-partition decomposition
   - Escalate: report to parent (sub-orchestrators only, last resort)
4. **Succession**: Self-succeed at 16 cumulative sub-agent spawns by writing handoff.md, spawning a successor of type teamwork_preview_orchestrator, and exiting.
- **Work items**:
  1. Decompose project requirements into milestones and create PROJECT.md [in-progress]
  2. Spawn E2E Testing Track Orchestrator [pending]
  3. Spawn Implementation Track Sub-orchestrators [pending]
  4. Coordinate and verify milestone completions [pending]
  5. Final project E2E validation and reporting [pending]
- **Current phase**: 1
- **Current focus**: Milestone decomposition and E2E track setup

## 🔒 Key Constraints
- CODE_ONLY network mode: No external HTTP client requests, only code_search and other local filesystem/command tools.
- NEVER write, modify, or create source code files directly (only metadata/state markdown files in .agents/).
- Every code change must be verified by a worker/reviewer team before passing the gate.
- Commit and push all code changes to GitHub (gemini rule).
- Never reuse a subagent after it has delivered its handoff.

## Current Parent
- Conversation ID: 7ccda073-6af2-494c-b1e9-ba73ad602283
- Updated: not yet

## Key Decisions Made
- Selected Project Pattern for orchestrating this multi-faceted enhancement task.
- Chose to create a top-level PROJECT.md and spawn a separate E2E Testing Track Orchestrator and Implementation Sub-orchestrators.

## Team Roster
| Agent | Type | Work Item | Status | Conv ID |
|-------|------|-----------|--------|---------|
| sub_orch_e2e | self | E2E Testing Track | in-progress | 749277ef-938e-41b8-b477-496a70f7108e |
| sub_orch_impl | self | Implementation Track | in-progress | 443e1ef2-d22c-4e07-8ce9-787dd0059c8c |

## Succession Status
- Succession required: no
- Spawn count: 2 / 16
- Pending subagents: [749277ef-938e-41b8-b477-496a70f7108e, 443e1ef2-d22c-4e07-8ce9-787dd0059c8c]
- Predecessor: none
- Successor: not yet spawned

## Active Timers
- Heartbeat cron: task-17
- Safety timer: none
- On succession: kill all timers before spawning successor
- On context truncation: run `manage_task(Action="list")` — re-create if missing

## Artifact Index
- /home/emiloffingen/presek/.agents/orchestrator/ORIGINAL_REQUEST.md — Verbatim user request
- /home/emiloffingen/presek/.agents/orchestrator/BRIEFING.md — Persistent context briefing
