# Purplle AI Store Intelligence System — Architecture (DESIGN.md)

## System Overview

This system is an end-to-end AI-powered Store Intelligence pipeline that starts from raw CCTV footage and produces real-time business analytics — specifically the **Offline Store Conversion Rate** (visitors who completed a purchase ÷ total unique visitors). The pipeline is designed to handle real-world edge cases: group entry, staff movement, re-entry, partial occlusion, billing queue buildup, and empty store periods.

## Architecture Diagram

```
┌─────────────────┐     ┌──────────────────────────┐     ┌──────────────────┐
│  Raw CCTV Clips  │────▶│  Detection Pipeline       │────▶│  Event Stream     │
│  (15fps, 1080p)  │     │  YOLOv8 + ByteTrack       │     │  Pydantic Events  │
│  3 cameras/store │     │  ZoneMapper + ReIDManager  │     │  8 Event Types    │
└─────────────────┘     └──────────────────────────┘     └────────┬─────────┘
                                                                   │
                                                                   ▼
    ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────────┐
    │  Live Dashboard   │◀────│  FastAPI API      │◀────│  SQLite + Anomaly    │
    │  Glassmorphism UI │     │  /metrics /funnel  │     │  StorageEngine       │
    │  SVG Floor Plan   │     │  /heatmap /anomaly │     │  AnomalyDetector     │
    └──────────────────┘     └──────────────────┘     └──────────────────────┘
                                                            ▲
                                                            │
                                                   ┌───────┴────────┐
                                                   │ POS Correlation │
                                                   │ 5-min window    │
                                                   └────────────────┘
```

## Data Flow (End-to-End)

### Stage 1: Detection Pipeline
- **Input**: Raw CCTV clips (15fps, 1080p, 3 camera angles per store)
- **Processing**: Downsampled to 3 FPS (configurable 1–5) for efficiency. Each frame passes through YOLOv8 (person detection, `class=0`) → ByteTrack (multi-object tracking via `supervision`) → ZoneMapper (Shapely polygon point-in-zone tests against `store_layout.json`)
- **Coordinate Scaling**: Raw detection bounding boxes are auto-scaled from frame resolution (e.g. 1920×1080) to the zone coordinate system (defined in `store_layout.json`) to ensure consistent zone mapping regardless of video resolution
- **Staff Classification**: Persons detected in `STAFF_ONLY` zones are retroactively flagged as staff across all their events via `ReIDManager.mark_staff()`
- **Output**: Structured `EventSchema` objects (Pydantic-validated) emitted per-frame with 8 event types: ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL, BILLING_QUEUE_JOIN, BILLING_QUEUE_ABANDON, REENTRY

### Stage 2: Event Extraction & Session Logic
- **Visitor Lifecycle**: Each new ByteTrack ID maps to a unique `visitor_id` (UUID-based). Entry is emitted on first detection. EXIT is emitted after 10 seconds of no detection (stale-track cleanup)
- **Zone Transitions**: ZONE_ENTER/ZONE_EXIT are emitted on zone boundary crossings. Dwell time is computed from zone entry to zone exit timestamps
- **ZONE_DWELL**: Emitted every 30 continuous seconds within the same zone, as specified
- **Billing Logic**: Entering the BILLING zone emits BILLING_QUEUE_JOIN with `queue_depth` metadata. Exiting BILLING without a correlated POS transaction emits BILLING_QUEUE_ABANDON; with a POS match, it emits ZONE_EXIT (successful purchase)
- **Re-entry**: If a visitor's track reappears after an EXIT event, REENTRY is emitted instead of a new ENTRY

### Stage 3: POS Correlation & Streaming
- **POSCorrelator**: Parses `pos_transactions.csv`, indexes transactions by store and timestamp. A billing zone exit within 5 minutes before a POS transaction counts as a converted visitor
- **EventStreamer**: Batches events (default 100) and POSTs them to the API via `requests.Session` with `urllib3` retry adapters (3 retries, backoff). Buffer is fully drained on shutdown

### Stage 4: Storage & Analytics
- **SQLite** with WAL mode for concurrent read/write access. Three indexes: `(store_id, timestamp)`, `(store_id, visitor_id)`, `(event_type)` for fast analytical queries
- **Idempotent Ingestion**: `INSERT OR IGNORE` on `event_id` primary key — safe to replay events
- **Metrics**: Computed from latest event date (not `date('now')`) to handle both real-time and batch-processed data correctly

### Stage 5: Intelligence API (FastAPI)
- **Structured JSON Logging**: Every request logs `trace_id`, `store_id`, `endpoint`, `method`, `status_code`, `latency_ms`, `event_count`
- **Partial Success**: `/events/ingest` validates each event individually — malformed events are reported in the response, valid ones are ingested
- **Graceful Degradation**: Database failures return HTTP 503 with structured body, no raw stack traces

### Stage 6: Anomaly Detection
- **BILLING_QUEUE_SPIKE**: Real-time during ingestion. Fires when `queue_depth > threshold` (default 5). Severity escalates (WARN → CRITICAL) based on depth
- **DEAD_ZONE**: Checked on anomaly endpoint access. Zones with no visitor activity for >30 minutes flagged with resolution tracking
- **CONVERSION_DROP**: Compared against 7-day historical average. >20% drop triggers WARN, >40% triggers CRITICAL

### Stage 7: Live Dashboard
- Real-time polling (2-second interval) of all API endpoints
- Interactive SVG floor plan dynamically rendered from `store_layout.json` with traffic intensity heatmap overlay
- Customer journey funnel with drop-off percentages, dwell time comparison chart, anomaly alert feed with severity coloring

## AI-Assisted Decisions

### Where AI Shaped the Design — and Where I Overrode It

1. **Architecture Decomposition**: I used Claude to evaluate whether to use a monolithic pipeline vs. decoupled modules. AI suggested a microservices approach with Kafka for event streaming. I **disagreed** — for a containerised demo, HTTP batch streaming with retry is simpler, has fewer moving parts, and avoids the `docker-compose` complexity of running Kafka/Zookeeper. The trade-off is throughput (HTTP POST vs. Kafka consumer groups), but for the scale of this challenge (5 stores, 3 cameras each), HTTP is sufficient. I would switch to Kafka at 40+ stores.

2. **Event Schema Design**: AI suggested a flatter schema without nested `metadata`. I **agreed partially** — I kept the top-level fields flat for SQL storage efficiency, but retained the `metadata` sub-object for extensible fields (`queue_depth`, `sku_zone`, `session_seq`) that don't need indexed queries. This balances query performance with schema flexibility.

3. **Zone Mapping Strategy**: AI proposed using a VLM (GPT-4V) to classify zones from frame content. I **overrode this** — polygon-based zone mapping from `store_layout.json` is deterministic, has zero inference cost, and doesn't require API calls during real-time processing. A VLM would add latency and non-determinism to every frame. The trade-off is that zones must be pre-configured, but for fixed-camera retail installations, this is the correct approach.

4. **Staff Detection**: AI suggested training a custom classifier on uniform colors. I chose a **simpler heuristic** — mark anyone detected in the STAFF_ONLY zone as staff, then propagate that flag across all their events. This works because retail staff typically access back-of-store areas that customers don't. The limitation is staff who only work the floor without entering staff-only zones — documented as a known constraint.

## Privacy Model

- No facial recognition is used. All tracking is via bounding box position + ByteTrack motion correlation
- Track IDs and visitor IDs are ephemeral UUIDs — no persistent identity across store visits
- Only aggregate metrics are stored and exposed via API (unique visitor counts, conversion rates, zone dwell averages)
- The input CCTV footage has full-face blur applied and no audio

## Known Limitations

1. **Re-ID Across Exits**: The current Re-ID uses 1:1 track-to-visitor mapping. When a person leaves and returns, ByteTrack assigns a new track ID. True cross-session re-identification would require appearance-based feature extraction (e.g., OSNet) — this is a production improvement documented here for transparency
2. **Cross-Camera Deduplication**: Each camera is processed independently. Overlapping FOV areas may double-count visitors. Production fix: cross-camera Re-ID using feature vectors
3. **Staff Detection Gaps**: Staff who never enter STAFF_ONLY zones won't be flagged. Production fix: uniform classification model
4. **Single-Node SQLite**: At 40 live stores, the single SQLite file becomes a write bottleneck. Production fix: PostgreSQL/TimescaleDB with connection pooling
