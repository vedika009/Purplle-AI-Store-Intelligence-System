from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from typing import List, Dict, Any
from datetime import datetime, timezone
import logging
import json
import uuid
import os
import shutil

from src.storage.engine import StorageEngine
from src.cv_layer.schema import EventSchema
from src.anomaly.detector import AnomalyDetector

# ─── Structured JSON Logging ───────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    """Production-grade JSON log formatter with trace context."""
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Attach extra fields if present (trace_id, store_id, etc.)
        for key in ("trace_id", "store_id", "endpoint", "method", "status_code",
                     "latency_ms", "event_count", "inserted_count"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        return json.dumps(log_entry)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("api")

# ─── App Initialization ───────────────────────────────────────────────
app = FastAPI(title="Purplle Store Intelligence API")

# CORS — allow dashboard from any origin during review
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for the dashboard
os.makedirs("src/api/static", exist_ok=True)
if os.path.exists("store_layout.json"):
    shutil.copy("store_layout.json", "src/api/static/store_layout.json")
app.mount("/static", StaticFiles(directory="src/api/static", html=True), name="static")

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/static/index.html")

@app.get("/dashboard", include_in_schema=False)
async def dashboard():
    return RedirectResponse(url="/static/index.html")

# Initialize shared components
storage = StorageEngine("store_intelligence.db")
anomaly_detector = AnomalyDetector(queue_threshold=5)

# ─── Structured Logging Middleware ─────────────────────────────────────
@app.middleware("http")
async def structured_log_middleware(request: Request, call_next):
    trace_id = str(uuid.uuid4())[:12]
    request.state.trace_id = trace_id

    # Extract store_id from path if present
    store_id = None
    path_parts = request.url.path.strip("/").split("/")
    if "stores" in path_parts:
        idx = path_parts.index("stores")
        if idx + 1 < len(path_parts):
            store_id = path_parts[idx + 1]

    start_time = datetime.now(timezone.utc)
    try:
        response = await call_next(request)
        latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        logger.info(
            f"{request.method} {request.url.path} {response.status_code} {latency_ms:.1f}ms",
            extra={
                "trace_id": trace_id,
                "store_id": store_id,
                "endpoint": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "latency_ms": round(latency_ms, 1),
            }
        )
        response.headers["X-Trace-ID"] = trace_id
        return response
    except Exception as e:
        latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        logger.error(
            f"{request.method} {request.url.path} 500 {latency_ms:.1f}ms - {str(e)}",
            extra={
                "trace_id": trace_id,
                "store_id": store_id,
                "endpoint": request.url.path,
                "method": request.method,
                "status_code": 500,
                "latency_ms": round(latency_ms, 1),
            }
        )
        raise

# ─── Health Endpoint ───────────────────────────────────────────────────
@app.get("/health")
def health_check():
    try:
        last_events = storage.get_last_event_time_per_store()
        status = "healthy"
        lag_warning = None
        stores_status = {}

        now_utc = datetime.now(timezone.utc)

        for store_id, last_event in last_events.items():
            if last_event.tzinfo is None:
                last_event = last_event.replace(tzinfo=timezone.utc)
            lag = (now_utc - last_event).total_seconds()

            store_status = "healthy"
            store_warning = None
            if lag > 300:
                store_status = "degraded"
                store_warning = "STALE_FEED"
                status = "degraded"
                lag_warning = "STALE_FEED"

            stores_status[store_id] = {
                "status": store_status,
                "warning": store_warning,
                "last_event_timestamp": last_event.isoformat(),
                "lag_seconds": lag
            }

        return {
            "status": status,
            "warning": lag_warning,
            "stores": stores_status
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable: Database connection failed")

# ─── Event Ingestion with Partial Success ──────────────────────────────
@app.post("/events/ingest")
async def ingest_events(request: Request):
    """
    Accepts a JSON array of events. Validates each individually.
    Returns partial success: valid events are ingested, malformed ones are reported.
    Idempotent by event_id.
    """
    trace_id = getattr(request.state, "trace_id", "unknown")
    try:
        raw_body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "Invalid JSON body"}
        )

    if not isinstance(raw_body, list):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "Expected a JSON array of events"}
        )

    valid_events: List[EventSchema] = []
    errors: List[Dict[str, Any]] = []

    for idx, raw_event in enumerate(raw_body):
        try:
            event = EventSchema(**raw_event)
            valid_events.append(event)
        except (ValidationError, Exception) as e:
            event_id = raw_event.get("event_id", "unknown") if isinstance(raw_event, dict) else "unknown"
            errors.append({
                "index": idx,
                "event_id": event_id,
                "error": str(e) if not isinstance(e, ValidationError) else e.errors()
            })

    # Process anomalies for valid events
    for event in valid_events:
        anomaly = anomaly_detector.process_event(event)
        if anomaly:
            logger.info(
                f"Anomaly detected: {anomaly.anomaly_type.value}",
                extra={"trace_id": trace_id, "store_id": anomaly.store_id}
            )
            storage.insert_anomaly(anomaly)

    # Insert valid events to storage (idempotent — ignores duplicate event_ids)
    inserted = storage.insert_events(valid_events) if valid_events else 0

    logger.info(
        f"Ingested batch: {len(valid_events)} valid, {len(errors)} errors, {inserted} new",
        extra={
            "trace_id": trace_id,
            "event_count": len(raw_body),
            "inserted_count": inserted,
        }
    )

    return {
        "status": "partial_success" if errors else "success",
        "received": len(raw_body),
        "accepted": len(valid_events),
        "inserted": inserted,
        "errors": errors
    }

# ─── Analytics Endpoints ──────────────────────────────────────────────
@app.get("/stores/{store_id}/metrics")
def get_metrics(store_id: str):
    try:
        return storage.get_metrics(store_id)
    except Exception as e:
        logger.error(f"Failed to fetch metrics: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable")

@app.get("/stores/{store_id}/funnel")
def get_funnel(store_id: str):
    try:
        return storage.get_funnel(store_id)
    except Exception as e:
        logger.error(f"Failed to fetch funnel: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable")

@app.get("/stores/{store_id}/heatmap")
def get_heatmap(store_id: str):
    try:
        return storage.get_heatmap(store_id)
    except Exception as e:
        logger.error(f"Failed to fetch heatmap: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable")

@app.get("/stores/{store_id}/anomalies")
def get_anomalies(store_id: str):
    try:
        # Run active evaluations for dead zones and conversion drops
        latest_time = storage.get_last_event_time(store_id)
        if latest_time:
            if latest_time.tzinfo is None:
                latest_time = latest_time.replace(tzinfo=timezone.utc)
            # 1. Check dead zones
            known_zones = storage.get_known_zones(store_id)
            dead_zone_anomalies, resolved_zones = anomaly_detector.check_dead_zones(
                store_id, latest_time, known_zones
            )
            # Resolve zones that are active again
            storage.resolve_dead_zones(store_id, resolved_zones)
            # Insert any newly detected dead zone anomalies
            for anomaly in dead_zone_anomalies:
                storage.insert_anomaly(anomaly)

            # 2. Check conversion drops
            metrics = storage.get_metrics(store_id)
            current_cr = metrics.get("conversion_rate", 0.0)
            avg_7d_cr = storage.get_historical_average_cr(store_id, latest_time)

            cr_anomaly, cr_resolved = anomaly_detector.check_conversion_drop(
                store_id, latest_time, current_cr, avg_7d_cr
            )
            if cr_resolved:
                storage.resolve_conversion_drop(store_id)
            elif cr_anomaly:
                storage.insert_anomaly(cr_anomaly)

        return {
            "store_id": store_id,
            "active_anomalies": storage.get_active_anomalies(store_id)
        }
    except Exception as e:
        logger.error(f"Failed to fetch anomalies: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable")
