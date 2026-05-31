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
uvicorn src.api.app:app --reload
```

## Live Dashboard Demo (Phase 7)
To see the system in action with real-time updating metrics and funnel:

1. **Start the API server (if not already running):**
   ```bash
   uvicorn src.api.app:app --reload
   ```
2. **Open the Dashboard in your browser:**
   Navigate to [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
3. **Run the simulated pipeline:**
   In a new terminal, run the demo script to simulate store traffic and events:
   ```bash
   python -m src.demo_runner --simulate
   ```
Watch the dashboard update live as the simulated people browse, queue, and checkout!

## Documentation
- `DESIGN.md`: High-level system overview and end-to-end data flow.
- `CHOICES.md`: Explains core architectural decisions, models, streaming rationale, and edge-case handling.

## Features
- **Phase 1 & 2:** Video Ingestion and Computer Vision Layer (YOLOv8 + ByteTrack).
- **Phase 3:** Event Schema & Streaming (Batched HTTP POST).
- **Phase 4:** Anomaly Detection (Queue Spikes, Dead Zones, Conversion Drops).
- **Phase 5 & 6:** Storage Analytics (SQLite) & Production Intelligence API (FastAPI).
