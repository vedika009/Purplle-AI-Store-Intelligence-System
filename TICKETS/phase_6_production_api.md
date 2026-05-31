# Phase 6: Production Intelligence API

## Goal
Build a robust, containerized REST API to ingest events and serve analytics.

## Tasks
- [ ] Implement `POST /events/ingest`: Accepts batches of up to 500 events, validates, deduplicates, stores. Must be idempotent by `event_id`, handle partial success on malformed events, and return structured error response.
- [ ] Implement `GET /health`: Service status, last event timestamp per store, and `STALE_FEED` warning if lag > threshold.
- [ ] Implement `GET /stores/{id}/metrics`: Return today's unique visitors, conversion rate, avg dwell, queue depth, abandonment rate (excluding `is_staff=true`, handle zero-purchase stores).
- [ ] Implement `GET /stores/{id}/funnel`: Conversion funnel counts and drop-off % (session-based, deduplicate re-entries).
- [ ] Implement `GET /stores/{id}/heatmap`: Zone visit frequency + avg dwell (0-100 normalized, include `data_confidence` flag if <20 sessions).
- [ ] Implement `GET /stores/{id}/anomalies`: Active anomalies (queue spike, conversion drop, dead zone).
- [ ] Implement graceful degradation (HTTP 503 on DB down, no raw stack traces).
- [ ] Implement structured logging for every request (trace_id, store_id, endpoint, latency, etc.).

## Testing & Production Requirements
- [ ] Test statement coverage > 70%.
- [ ] Tests must cover API idempotency for `/events/ingest`.
- [ ] Add `# PROMPT:` and `# CHANGES MADE:` blocks to all test files.
- [ ] Create `docker-compose.yml` to start everything (`docker compose up`).
- [ ] README setup in 5 commands.
