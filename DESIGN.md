# Purplle AI Store Intelligence System — Architecture (DESIGN.md)

*Briefly outline the end-to-end data flow.*

(Refer to `store_intelligence_architecture.svg` for the visual overview.)

The system is built to ingest CCTV, detect people, stream events, aggregate metrics, and expose them via a FastAPI backend, ensuring business funnel metrics (Entered -> Browsed -> Checked out) are tracked accurately.

### Data Flow
1. **Ingestion & Computer Vision Layer**: Reads video streams, detects persons using YOLOv8, tracks them via ByteTrack (`supervision`), and maps bounding box positions to store zones defined in `store_layout.json`.
2. **Event Extraction**: Converts spatial tracking data into the required Event Schema, keeping track of session logic and tagging specific events like `REENTRY` and `ZONE_DWELL`.
3. **Correlation & Streaming**: Ingests `pos_transactions.csv` to correlate billing zone exits with purchases vs. queue abandonment. Streams batched events via HTTP to the Intelligence API.
4. **Storage Engine**: Persists the events in a local SQLite database (`store_intelligence.db`), allowing performant analytical queries (metrics, funnel drop-off, heatmaps).
5. **Intelligence API**: Exposes FastAPI endpoints for ingestion, health checks, metrics, funnels, heatmaps, and active anomaly alerts.
