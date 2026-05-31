Here's a comprehensive, battle-tested plan for the Purplle AI Store Intelligence System:Here's the full plan, broken into phases you can execute sequentially:

---

## **Phase 1 — Video ingestion & frame pipeline**

**Goal:** Reliable, low-latency frame extraction from raw CCTV footage.

**What to build:**

* A multi-source ingestion service that reads RTSP streams (or reads from uploaded video files for the demo) using OpenCV or FFmpeg. Support N cameras via a config file.  
* A **frame sampler** — don't process every frame; 1–3 fps is usually sufficient for retail footfall analytics and reduces GPU load by 20×. Make the rate configurable per camera.  
* A lightweight **pre-processor**: resize to the model's input resolution (640×640 for YOLO), normalize, optionally denoise (OpenCV bilateral filter works well on cheap IP cameras).  
* Write sampled frames to an object store (S3-compatible, or local disk for the demo) with a structured key: `{store_id}/{camera_id}/{timestamp}.jpg`.

**Key decision to document:** Why 1–5 fps? Because dwell time and queue depth are temporal aggregates — you don't need 30fps accuracy. Include this reasoning explicitly; the judges want to see trade-off thinking.

---

## **Phase 2 — Computer vision layer**

**What to build:**

* **Person detector:** Use YOLOv8n or YOLOv8s (nano/small — fast enough for near-real-time on CPU, excellent on GPU). Alternatively RT-DETR if you want to demonstrate awareness of transformer-based detectors. Filter to `person` class only.  
* **Multi-object tracker:** ByteTrack (best recall/speed trade-off) or BoT-SORT. This gives each person a consistent track ID across frames, which is essential for dwell-time calculation.  
* **Zone mapper:** Define store zones (entrance, beauty aisle, checkout, etc.) as named polygons in a config JSON. Use `shapely` for point-in-polygon checks. This is where you convert bounding box centroids into semantic events.  
* **Event extractor:** From track \+ zone data, emit structured events:  
  * `PersonEntered(zone, track_id, timestamp)`  
  * `PersonExited(zone, track_id, timestamp, dwell_seconds)`  
  * `QueueDepth(zone, count, timestamp)`  
  * `CrowdAlert(zone, density, timestamp)` when count exceeds threshold

**Key decision to document:** Why not a separate pose/action recognition model? For this use case, zone-based spatial logic gives 80% of the value at 20% of the complexity. Mention this as a deliberate scope decision.

---

## **Phase 3 — Event streaming**

**What to build:**

* **Kafka** (or Redpanda for a lighter-weight demo) as the event bus. Define topics: `store.events.entry`, `store.events.dwell`, `store.events.queue`, `store.events.anomaly`.  
* Events should be JSON or Avro-serialized. Include `store_id`, `camera_id`, `zone`, `timestamp`, and the metric value.  
* **Faust** (Python, simpler) or **Apache Flink** (Java/Python, more production-grade) as the stream processor. Implement:  
  * **Tumbling windows** (e.g., 5-minute buckets) for footfall counts per zone.  
  * **Session windows** for individual dwell-time aggregation per track ID.  
  * **Sliding windows** for rolling averages used by the anomaly detector.

**Key decision to document:** Why Kafka over a simple queue? Replay capability — if the CV model is updated, you can re-process historical events. This is a strong production argument.

---

## **Phase 4 — Anomaly detection**

**What to build:**

* **Statistical baseline:** Compute hourly/daily mean and standard deviation of footfall, queue depth, and dwell time per zone, per day-of-week. Seed with synthetic data for the demo.  
* **Isolation Forest** (scikit-learn) trained on the baseline features. This works well for multivariate anomalies without needing labeled data.  
* Alternatively, a simple **Z-score** detector is more explainable — flag anything beyond ±2.5σ. Mention both approaches; use Z-score as fallback.  
* **Alert types to detect:**  
  * Unusual crowd density (safety risk)  
  * Abandoned zone (no traffic during open hours — display/layout problem?)  
  * Queue exceeding threshold (staff allocation signal)  
  * Dwell spike in a specific zone (high engagement or confusion)  
* Route alerts to a webhook (Slack/Teams-compatible) and also write them to the DB with severity and a natural-language description.

---

## **Phase 5 — Storage & analytics**

**What to build:**

* **TimescaleDB** (PostgreSQL extension) for time-series metrics — it handles hypertable partitioning automatically and works with standard SQL. Schema: one row per (store, camera, zone, 5-min window) with aggregated counts.  
* **Redis** for sub-second reads needed by the live dashboard — cache the latest window's metrics per zone.  
* Pre-compute a **heatmap** per camera per hour: a 2D grid where each cell is the normalized count of bounding box centroids passing through it. Store as a JSON matrix or PNG overlay.

---

## **Phase 6 — Production API**

**What to build with FastAPI:**

| Endpoint | Description |
| ----- | ----- |
| `GET /stores/{id}/footfall` | Hourly/daily footfall counts with time range |
| `GET /stores/{id}/heatmap` | Zone heatmap for a given time window |
| `GET /stores/{id}/queue` | Current \+ historical queue depth by zone |
| `GET /stores/{id}/anomalies` | Recent anomaly log with severity \+ description |
| `WS /stores/{id}/live` | WebSocket for real-time metric push |
| `POST /stores/{id}/zones` | Update zone polygon definitions |

* Add JWT auth (or API key header for simplicity).  
* Rate limit with `slowapi`.  
* Serve Swagger UI at `/docs` — this is important for the demo.  
* Write a Pydantic model for every request/response — shows production discipline.

---

## **Phase 7 — Dashboard & demo**

**What to build:**

* A simple Grafana dashboard (if time-constrained) or a custom React/Next.js frontend with:  
  * Live footfall line chart per zone  
  * Store floor plan SVG with color-coded zone density overlays  
  * Anomaly alert log with timestamps  
  * A "replay" mode that scrubs through a recorded session  
* Docker Compose file that spins up the entire stack (Kafka, TimescaleDB, Redis, API, CV worker) in one command.

---

## **Architecture decisions to document explicitly**

These are the questions the judges will ask:

**Why not a cloud CV API (e.g., Rekognition)?** Latency, cost at scale, and data privacy for store footage. On-device or self-hosted inference gives sub-200ms per frame and keeps footage on-prem.

**Why Kafka over a REST fan-out?** Event replay, decoupling of producers from consumers, and the ability to add new consumers (e.g., an LLM summarizer) without touching the CV pipeline.

**How do you handle camera occlusion and track loss?** Mention that ByteTrack handles short occlusions via a "lost" buffer with re-association. For long occlusions (\>N frames), the track is terminated and a new one assigned — this introduces some dwell-time undercounting which is acceptable at retail scale.

**What's the privacy model?** No facial recognition. Track IDs are ephemeral (reset every session). Only aggregate metrics are stored. Raw frames are optionally purged after N hours.

**What would you scale next?** Horizontal CV workers (one per camera), a GPU inference server (Triton), and Kafka partition per camera. The current design scales to \~20 cameras before needing sharding.

---

## **Suggested timeline (if you have 24–48 hours)**

| Hours | Deliverable |
| ----- | ----- |
| 0–4 | Frame pipeline \+ YOLO detection working on a sample video |
| 4–10 | Tracker \+ zone mapper \+ event emission |
| 10–14 | Kafka \+ Faust stream processing \+ TimescaleDB writes |
| 14–18 | Anomaly detector \+ alert webhook |
| 18–22 | FastAPI with all endpoints \+ Redis caching |
| 22–26 | Dashboard \+ Docker Compose \+ README |
| 26–30 | Polish, load test, write architecture doc |

The README and architecture doc carry serious weight in this kind of challenge. Write it as if you're handing the system to a new engineer — explain every major decision, what you'd do differently with more time, and what the known limitations are.

