from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from typing import List
from datetime import datetime, timezone
import logging
import os

from src.storage.engine import StorageEngine
from src.cv_layer.schema import EventSchema
from src.anomaly.detector import AnomalyDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI(title="Purplle Store Intelligence API")

# Mount static files for the dashboard
os.makedirs("src/api/static", exist_ok=True)
import shutil
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

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    try:
        response = await call_next(request)
        process_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.4f}s")
        return response
    except Exception as e:
        process_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"{request.method} {request.url.path} - 500 - {process_time:.4f}s - {str(e)}")
        raise

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

@app.post("/events/ingest")
def ingest_events(events: List[EventSchema]):
    try:
        # 1. Process inline anomalies
        for event in events:
            anomaly = anomaly_detector.process_event(event)
            if anomaly:
                logger.info(f"Anomaly detected: {anomaly.anomaly_type.value} | Store: {anomaly.store_id} | Zone: {anomaly.zone_id} | Depth: {anomaly.description}")
                storage.insert_anomaly(anomaly)
                
        # 2. Insert to storage (idempotent, handles partial success natively by ignoring duplicates)
        inserted = storage.insert_events(events)
        logger.info(f"Ingested {len(events)} events (inserted {inserted} new events)")
        
        return {"status": "success", "inserted": inserted, "received": len(events)}
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable: Storage backend failed")

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
