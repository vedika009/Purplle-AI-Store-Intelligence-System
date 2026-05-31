# PROMPT: Implement tests for the FastAPI application created in Phase 6, verifying all endpoints (/health, /events/ingest, metrics, funnel, heatmap, anomalies). Ensure statement coverage > 70% and verify API idempotency for `/events/ingest`.
# CHANGES MADE: Added `tests/test_api.py` with `fastapi.testclient.TestClient`. Mocked the `StorageEngine` and `AnomalyDetector` components where necessary or used a fresh in-memory database to test idempotency and full integration logic.

import pytest
import os
from fastapi.testclient import TestClient
import uuid
from datetime import datetime, timezone, timedelta

# Override DB path for tests before importing app
from src.api.app import app, storage
test_db_path = "test_store_intelligence.db"
if os.path.exists(test_db_path):
    os.remove(test_db_path)
storage.db_path = test_db_path
storage._init_db()

from src.cv_layer.schema import EventType

client = TestClient(app)

def create_event_payload(event_type: str, visitor_id: str, zone_id: str = None, queue_depth: int = 0):
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": "store_test",
        "camera_id": "cam_1",
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "zone_id": zone_id,
        "dwell_ms": 5000,
        "is_staff": False,
        "confidence": 0.95,
        "metadata": {
            "queue_depth": queue_depth,
            "session_seq": 1
        }
    }

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data

def test_ingest_events_and_idempotency():
    # 1. Generate payload
    event = create_event_payload(EventType.ENTRY.value, "visitor_1")
    
    # 2. Ingest once
    response1 = client.post("/events/ingest", json=[event])
    assert response1.json()["accepted"] == 1
    assert response1.json()["inserted"] == 1
    
    # 3. Ingest exactly the same event again (Idempotency check)
    response2 = client.post("/events/ingest", json=[event])
    assert response2.json()["accepted"] == 1
    assert response2.json()["inserted"] == 0 # Should ignore duplicate

def test_metrics_endpoint():
    # Setup some test data directly via endpoints
    v2_entry = create_event_payload(EventType.ENTRY.value, "visitor_2")
    v2_join = create_event_payload(EventType.BILLING_QUEUE_JOIN.value, "visitor_2", "BILLING", queue_depth=1)
    v2_exit = create_event_payload(EventType.ZONE_EXIT.value, "visitor_2", "BILLING")
    
    client.post("/events/ingest", json=[v2_entry, v2_join, v2_exit])
    
    response = client.get("/stores/store_test/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "unique_visitors_today" in data
    assert data["unique_visitors_today"] >= 1
    assert "conversion_rate" in data

def test_funnel_endpoint():
    response = client.get("/stores/store_test/funnel")
    assert response.status_code == 200
    data = response.json()
    assert "funnel" in data
    assert len(data["funnel"]) == 4

def test_heatmap_endpoint():
    response = client.get("/stores/store_test/heatmap")
    assert response.status_code == 200
    data = response.json()
    assert "zones" in data

def test_anomalies_endpoint():
    # Trigger a queue spike
    spike_event = create_event_payload(EventType.BILLING_QUEUE_JOIN.value, "visitor_3", "BILLING", queue_depth=15)
    client.post("/events/ingest", json=[spike_event])
    
    response = client.get("/stores/store_test/anomalies")
    assert response.status_code == 200
    data = response.json()
    assert "active_anomalies" in data
    assert len(data["active_anomalies"]) >= 1
    assert data["active_anomalies"][0]["anomaly_type"] == "QUEUE_SPIKE"

def test_api_dwell_per_zone():
    response = client.get("/stores/store_test/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "avg_dwell_per_zone" in data
    assert isinstance(data["avg_dwell_per_zone"], dict)

def test_api_health_per_store():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "stores" in data
    assert "store_test" in data["stores"]
    assert "last_event_timestamp" in data["stores"]["store_test"]

def test_api_historical_date_filter():
    # Ingest a historical event (April 10, 2026)
    hist_time = datetime(2026, 4, 10, 15, 0, 0, tzinfo=timezone.utc)
    hist_event = {
        "event_id": str(uuid.uuid4()),
        "store_id": "store_historical",
        "camera_id": "cam_1",
        "visitor_id": "vis_hist_1",
        "event_type": EventType.ENTRY.value,
        "timestamp": hist_time.isoformat(),
        "dwell_ms": 0,
        "is_staff": False,
        "confidence": 0.95,
        "metadata": {
            "session_seq": 1
        }
    }
    
    # Ingest event
    ingest_resp = client.post("/events/ingest", json=[hist_event])
    assert ingest_resp.status_code == 200
    assert ingest_resp.json()["inserted"] == 1
    
    # Query metrics for store_historical
    # It should correctly identify April 10, 2026 as the latest date and return 1 visitor
    metrics_resp = client.get("/stores/store_historical/metrics")
    assert metrics_resp.status_code == 200
    metrics_data = metrics_resp.json()
    assert metrics_data["unique_visitors_today"] == 1
