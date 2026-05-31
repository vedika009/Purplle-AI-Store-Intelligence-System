# Purplle AI Store Intelligence System — Decisions (CHOICES.md)

## Decision 1: Detection Model Selection

**Decision:** YOLOv8 + ByteTrack (via `supervision` library) for detection and tracking.

**Options Considered:**
| Option | Pros | Cons |
|--------|------|------|
| YOLOv8 + ByteTrack | Fast inference, robust tracking through occlusion, single-pass | No built-in Re-ID for cross-session tracking |
| YOLOv9 + DeepSORT | Marginally better accuracy, appearance-based Re-ID | Slower inference, heavier dependencies |
| RT-DETR + StrongSORT | Transformer-based, strong at crowded scenes | Much heavier compute, overkill for 3 FPS retail |
| MediaPipe | Lightweight, runs on CPU | Poor multi-person tracking, no zone mapping |

**What AI suggested:** Claude recommended YOLOv8 + DeepSORT for the appearance-based Re-ID capability, which would enable cross-exit Re-ID (REENTRY detection). GPT-4 suggested RT-DETR for better accuracy with overlapping people.

**What I chose and why:** I went with YOLOv8 + ByteTrack because:
1. ByteTrack uses IoU-based association which is faster and sufficient at 3 FPS where displacement between frames is ~0.46m — small enough for reliable association
2. DeepSORT's appearance features would help with REENTRY but add ~40% latency per frame. For the challenge scope (5 stores, 20-minute clips), the accuracy/speed trade-off favors ByteTrack
3. The `supervision` library wraps both model and tracker cleanly, reducing integration complexity

**Trade-off accepted:** Without appearance-based Re-ID, true cross-exit re-entry detection relies on track ID persistence. This means REENTRY events may underfire. I documented this as a known limitation and would add OSNet-based Re-ID in production.

---

## Decision 2: Event Schema Design

**Decision:** Strict Pydantic model (`EventSchema`) with explicit `EventType` Enum (8 types) and a nested `metadata` sub-object.

**Options Considered:**
| Approach | Pros | Cons |
|----------|------|------|
| Flat schema, all fields top-level | Simple SQL mapping, easy queries | Inflexible, NULL-heavy columns |
| Nested metadata + flat core fields | Core fields indexed in SQL, extensible metadata | Slightly more complex validation |
| Fully dynamic/schemaless (JSON blob) | Maximum flexibility | No validation, error-prone, poor query performance |

**What AI suggested:** Claude initially proposed a fully flat schema with every field at the top level, including `queue_depth`, `sku_zone`, and `session_seq`. ChatGPT suggested a JSON blob approach for maximum flexibility.

**What I chose and why:** I used a **hybrid approach** — core event fields (`event_id`, `store_id`, `visitor_id`, `event_type`, `timestamp`, `zone_id`, `dwell_ms`, `is_staff`, `confidence`) are top-level and directly mapped to SQL columns with indexes. Contextual fields (`queue_depth`, `sku_zone`, `session_seq`) are in a Pydantic `EventMetadata` sub-model. This gives us:
- Indexed SQL queries on the fields that matter for analytics (store_id, visitor_id, event_type, timestamp)
- Type-safe validation via Pydantic at ingestion time
- Extensibility for future metadata without schema migrations

**Where I disagreed with AI:** AI suggested making `dwell_ms` optional. I kept it required with a default of 0 for instantaneous events — this ensures every event has a consistent shape, which simplifies downstream aggregation queries.

---

## Decision 3: API Architecture — SQLite + HTTP Streaming (No Kafka)

**Decision:** SQLite with WAL mode for storage. HTTP POST batches for event streaming. No message queue.

**Options Considered:**
| Approach | Pros | Cons |
|----------|------|------|
| SQLite + HTTP POST | Zero infrastructure, fast setup, portable | Single-writer bottleneck at scale |
| PostgreSQL + Kafka | Production-grade, concurrent writes, consumer groups | Heavy infra, complex docker-compose |
| Redis Streams + PostgreSQL | Low-latency pub/sub + durable storage | Two databases to manage, overkill for demo |

**What AI suggested:** Both Claude and ChatGPT strongly recommended Kafka for event streaming, citing "real production systems always use a message queue." GPT-4 additionally suggested Redis as a caching layer for metrics.

**What I chose and why:** I **explicitly rejected Kafka** for this challenge because:
1. `docker compose up` must work without manual intervention. Kafka + Zookeeper adds 2 containers, 512MB+ RAM, and 30+ seconds to startup. The evaluation gate gives no tolerance for setup failures
2. SQLite in WAL mode handles concurrent reads + sequential writes. At the challenge scale (5 stores × 3 cameras × 3 FPS = ~45 events/second max), SQLite throughput is not the bottleneck
3. HTTP POST with `urllib3` retry adapters provides at-least-once delivery. Combined with idempotent ingestion (`INSERT OR IGNORE` on `event_id`), this gives the same correctness guarantee as Kafka for this scale

**What breaks at 40 stores:** SQLite's single-writer lock becomes a bottleneck at ~200+ events/second. I would switch to PostgreSQL with connection pooling (pgBouncer) and replace HTTP streaming with Kafka consumer groups partitioned by `store_id`. This is documented in DESIGN.md and I'm prepared to discuss it in the follow-up questions.

---

## Additional Design Decisions

### Staff Filtering Strategy
**Decision:** Zone-based staff detection — persons entering `STAFF_ONLY` zones are flagged as staff across all their events.

**What AI suggested:** Train a lightweight classification model on staff uniform colors extracted from the first 100 frames. I **disagreed** — this requires labeled training data we don't have, and uniform styles may vary across stores. The zone-based approach is deterministic and requires zero training.

**Known limitation:** Staff who never enter staff-only areas won't be flagged. In production, I'd combine zone heuristics with a temporal heuristic (people detected for >60 minutes continuously are likely staff).

### POS Correlation Window
**Decision:** 5-minute sliding window for correlating billing zone exits with POS transactions.

**Rationale:** The problem statement specifies: "A visitor who was in the billing zone in the 5-minute window before a transaction timestamp counts as a converted visitor." The `POSCorrelator` parses `pos_transactions.csv`, indexes by store and timestamp, and performs efficient binary search on the sorted transaction list. The correlation happens at event emission time (in `EventExtractor`), which means the pipeline must have POS data loaded to correctly classify billing exits. Events replayed without POS context will default to `BILLING_QUEUE_ABANDON`.

### Anomaly Detection Approach
**Decision:** Three anomaly types with different detection strategies:
- **BILLING_QUEUE_SPIKE**: Real-time during event ingestion (instantaneous check on `queue_depth` metadata)
- **DEAD_ZONE**: Lazy evaluation on `/anomalies` API access (time-delta check against zone last-seen state)
- **CONVERSION_DROP**: Computed on API access by comparing current conversion rate against 7-day rolling historical average

**What AI suggested:** Use Isolation Forest for statistical anomaly detection. I **chose threshold-based rules** because: (1) we don't have enough historical data for ML-based baselines, (2) threshold-based rules are transparent and debuggable, (3) the anomaly types are well-defined business rules, not statistical outliers.
