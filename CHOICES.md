# Purplle AI Store Intelligence System — Decisions (CHOICES.md)

*Front-load your reasoning: State the decision first, then the rationale.*

### Staff Filtering
**Decision:** We will use designated staff-entry zones to tag track IDs as "staff".
**Rationale:** This avoids complex re-identification models. Staff entering through the front door are manually mapped if necessary, but designated zones offer the most reliable, low-complexity solution for the demo.

### Edge Case Handling
*   **Re-entry (Same person leaves and returns):** Track IDs are ephemeral per session. If a person leaves and returns, they are treated as a new unique visit. This ensures funnel metrics don't get skewed by the same person walking in and out repeatedly.
*   **Group Entry:** Our zone-based logic counts bounding box centroids. While group entries can cause detection overlaps, ByteTrack’s re-association buffer helps maintain individual track IDs even if they briefly cluster.
*   **Occlusion (Person hidden behind display):** ByteTrack maintains a "lost" buffer. If a track is occluded for <N frames, it re-associates the ID. For longer occlusions, the track is terminated.

### Streaming & POS Correlation (Phase 3)
**Decision:** We stream events via synchronous HTTP POST batches using `requests.Session` with `urllib3` retry adapters. POS transactions are correlated locally using `POSCorrelator`.
**Rationale:** While Kafka is mentioned as an option, for the constraints of this demo/challenge and to minimize infrastructure overhead, a batched HTTP POST with retries to the Intelligence API provides sufficient decoupling and robustness. POS correlation is integrated directly into the `EventExtractor` (via `POSCorrelator`) to immediately emit `BILLING_QUEUE_ABANDON` vs `ZONE_EXIT` instead of relying on a complex downstream join in the streaming pipeline.

### Anomaly Detection (Phase 4)
**Decision:** `AnomalyDetector` operates on the event stream, evaluating queue spikes instantaneously on `BILLING_QUEUE_JOIN` events, while dead zones and conversion drops are checked periodically against accumulated state and historical averages.
**Rationale:** Queue depth anomalies are real-time operational issues and must be flagged instantly. Dead zones require a time-delta check which is better suited for a periodic CRON/timer job against last-seen state rather than purely event-driven logic (since the absence of events defines a dead zone).

### Storage & Intelligence API (Phase 5 & 6)
**Decision:** We use `FastAPI` combined with a local `SQLite` storage engine (`store_intelligence.db`). The API provides full idempotency on `/events/ingest` and runs complex analytical queries directly against indexed SQL tables.
**Rationale:** SQLite is extremely fast, local, requires no external infrastructure, and easily supports the complex aggregations (COUNT DISTINCT, GROUP BY, date filtering) required for metric and funnel computation. FastAPI enables high-concurrency ingestion and structured logging. Graceful degradation is achieved by catching connection errors and returning standard `503 Service Unavailable` responses.
