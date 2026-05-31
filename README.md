# Purplle AI Store Intelligence System

 This system is an AI-powered Store Intelligence System that processes raw CCTV footage, extracts analytical events, tracks conversions against POS data, and serves real-time insights via a FastAPI backend.

## Quickstart (5 Commands)

1. **Clone the repository:**
   ```bash
   git clone <your-repo> && cd purplle-ai-store-intelligence-system
   ```

2. **Set up virtual environment & install dependencies:**
   ```bash
   python -m venv venv && venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Run the complete test suite:**
   ```bash
   pytest tests/ -v
   ```

4. **Start the Intelligence API using Docker Compose:**
   ```bash
   docker compose up --build -d
   ```

5. **Test the Health Endpoint:**
   ```bash
   curl http://localhost:8000/health
   ```

You can also run the API locally without Docker:
```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

## Live Dashboard & Real Video pipeline (Phase 7)
To see the system in action:

1. **Start the API server (if not already running):**
   ```bash
   uvicorn src.api.app:app --host 0.0.0.0 --port 8000
   ```
2. **Open the Dashboard in your browser:**
   Navigate to [http://localhost:8000/dashboard](http://localhost:8000/dashboard)

3. **Option A: Run the simulated pipeline** (for quick verification of the dashboard interface):
   ```bash
   python -m src.demo_runner --simulate
   ```

4. **Option B: Run the pipeline on real CCTV clips & POS Data:**
   You can run the end-to-end computer vision tracking and correlation pipeline on the real video clips (`.mp4`) and real POS transaction data (`.csv`):
   ```bash
   # Activate the virtual environment
   venv\Scripts\activate

   # Run the pipeline runner on CAM 1, correlating with the real POS CSV file
   python -m src.pipeline_runner --video "./data/raw/CCTV Footage-20260529T160731Z-3-00144614ea/CCTV Footage/CAM 1.mp4" --pos-csv "./data/raw/Brigade_Bangalore_10_April_26 (1)bc6219c.csv" --camera-id "cam_1" --store-id "purplle_brigade_road" --max-frames 200
   ```
   **Key Configuration Options:**
   - `--video`: Path to the raw CCTV video (`.mp4`) clip.
   - `--pos-csv`: Path to the real POS transactions (`.csv`) file for correlation.
   - `--max-frames`: Limit the number of processed frames (e.g. `200`) for quick tests, or omit to process the entire video.
   - `--sample-fps`: Set target processing rate (default: `3` FPS).
   - `--show-preview`: Add this flag to open a real-time OpenCV window showing visual YOLO detection boxes, tracker IDs, and store zone polygons overlaid on the video frame.

Watch the dashboard update live as the real/simulated people browse, queue, and checkout!

## Documentation
- `DESIGN.md`: High-level system overview and end-to-end data flow.
- `CHOICES.md`: Explains core architectural decisions, models, streaming rationale, and edge-case handling.

## Features
- **Phase 1 & 2:** Video Ingestion and Computer Vision Layer (YOLOv8 + ByteTrack).
- **Phase 3:** Event Schema & Streaming (Batched HTTP POST).
- **Phase 4:** Anomaly Detection (Queue Spikes, Dead Zones, Conversion Drops).
- **Phase 5 & 6:** Storage Analytics (SQLite) & Production Intelligence API (FastAPI).
- **Part E Dashboard:** Live dashboard available at [http://localhost:8000/dashboard](http://localhost:8000/dashboard) — shows real-time KPIs, interactive SVG floor plan heatmap, customer journey funnel, and anomaly alerts.

## API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service status, per-store lag, STALE_FEED warnings |
| `/events/ingest` | POST | Batch event ingestion with partial success and idempotency |
| `/stores/{id}/metrics` | GET | Unique visitors, conversion rate, avg dwell, queue depth |
| `/stores/{id}/funnel` | GET | Entry → Browse → Queue → Purchase with drop-off % |
| `/stores/{id}/heatmap` | GET | Zone visit frequency (0-100) and avg dwell |
| `/stores/{id}/anomalies` | GET | Active anomalies: queue spike, dead zone, conversion drop |
