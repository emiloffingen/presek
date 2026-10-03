# Presek 10/10 Roadmap

## Phase 1: Production Reliability

- One Alembic head and repeatable clean-database upgrade
- Runtime schema contract check for every public API dependency
- Smoke checks for homepage, news API, ingestion, Redis, and disabled checkout
- No silent background-task failures for MK-only features

Gate: a clean deployment can migrate, start, ingest, and render the homepage without database errors.

## Phase 2: Product Clarity

- One primary homepage story, a short supporting set, then the latest feed
- Advanced analysis remains available but is secondary
- Every story exposes freshness, source count, and synthesis state
- Empty, degraded, and paused states explain what happened and what to do next

Gate: a first-time reader understands the product in ten seconds.

## Phase 3: Performance

- Cache the homepage response for a short, explicit TTL
- Keep secondary modules lazy and non-blocking
- Enforce image dimensions, responsive sources, and bounded payloads
- Track server response time and client-side loading milestones

Gate: the homepage feels instant on a mid-range mobile connection.

## Phase 4: Macedonian Editorial Quality

- Review all public copy in natural Macedonian
- Keep source attribution and grouping explanations visible
- Separate original reporting, aggregation, and generated analysis
- Automatically quarantine repeatedly failing feeds

Gate: every visible claim has a clear source or system-status explanation.

## Phase 5: Monetization

- Keep checkout hidden until Stripe keys and webhook verification are configured
- Test successful, failed, expired, duplicate, and mismatched sessions
- Add authenticated campaign access and delivery reporting

Gate: a real payment can be reconciled end-to-end without manual database edits.
