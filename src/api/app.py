from fastapi import FastAPI, HTTPException, Request
from typing import List
from datetime import datetime, timezone
import logging

from src.storage.engine import StorageEngine
from src.cv_layer.schema import EventSchema
from src.anomaly.detector import AnomalyDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI(title="Purplle Store Intelligence API")

# Initialize shared components
storage = StorageEngine("store_intelligence.db")
anomaly_detector = AnomalyDetector()

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
        # Simple query to test DB
        last_event = storage.get_last_event_time()
        status = "healthy"
        lag_warning = None
        
        if last_event:
            # Check if lag is > 5 minutes
            lag = (datetime.now(timezone.utc) - last_event).total_seconds()
            if lag > 300: 
                status = "degraded"
                lag_warning = "STALE_FEED"
                
        return {
            "status": status,
            "warning": lag_warning,
            "last_event_timestamp": last_event
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        # Graceful degradation (HTTP 503 on DB down, no raw stack traces)
        raise HTTPException(status_code=503, detail="Service Unavailable: Database connection failed")

@app.post("/events/ingest")
def ingest_events(events: List[EventSchema]):
    try:
        # 1. Process inline anomalies
        for event in events:
            anomaly = anomaly_detector.process_event(event)
            if anomaly:
                storage.insert_anomaly(anomaly)
                
        # 2. Insert to storage (idempotent, handles partial success natively by ignoring duplicates)
        inserted = storage.insert_events(events)
        
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
        return {
            "store_id": store_id, 
            "active_anomalies": storage.get_active_anomalies(store_id)
        }
    except Exception as e:
        logger.error(f"Failed to fetch anomalies: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable")
