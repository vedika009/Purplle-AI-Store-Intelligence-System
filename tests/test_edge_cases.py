# PROMPT: "Generate pytest edge case tests for the Store Intelligence API covering:
# empty store (zero events), all-staff clip, zero purchases, re-entry in funnel,
# and partial success on malformed event ingestion."
# CHANGES MADE: Added actual fixture-based setup with proper event schemas, added
# conftest-style helper, verified funnel dedup logic, fixed assertion on new partial
# success response format.

import pytest
import os
import sys
from datetime import datetime, timezone
from fastapi.testclient import TestClient

# Setup test database before importing app
os.environ["STORE_INTELLIGENCE_DB"] = "test_edge_cases.db"

from src.api.app import app, storage
from src.cv_layer.schema import EventSchema, EventType, EventMetadata

client = TestClient(app)

# ─── Test Fixtures ──────────────────────────────────────────────────

STORE_ID = "STORE_TEST_001"
BASE_TIME = datetime(2026, 4, 10, 14, 0, 0, tzinfo=timezone.utc)

def _make_event(event_type: str, visitor_id: str, zone_id=None,
                dwell_ms=0, is_staff=False, confidence=0.92,
                queue_depth=None, session_seq=1, timestamp=None,
                event_id=None) -> dict:
    """Helper to create a valid event dict for ingestion."""
    import uuid
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "store_id": STORE_ID,
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": (timestamp or BASE_TIME).isoformat(),
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": confidence,
        "metadata": {
            "queue_depth": queue_depth,
            "sku_zone": zone_id,
            "session_seq": session_seq
        }
    }


@pytest.fixture(autouse=True)
def clean_db():
    """Ensure clean database state for each test."""
    storage.db_path = "test_edge_cases.db"
    storage._init_db()
    with storage._get_conn() as conn:
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM anomalies")
        conn.commit()
    yield
    # Cleanup
    if os.path.exists("test_edge_cases.db"):
        try:
            os.remove("test_edge_cases.db")
        except PermissionError:
            pass


# ─── Edge Case: Empty Store ─────────────────────────────────────────

class TestEmptyStore:
    """When a store has zero events, all endpoints must return valid responses
    with zero/empty values — not crash or return null."""

    def test_metrics_empty_store(self):
        """GET /metrics for a store with no events should return zeros, not error."""
        response = client.get(f"/stores/{STORE_ID}/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["unique_visitors_today"] == 0
        assert data["conversion_rate"] == 0.0
        assert data["current_queue_depth"] == 0

    def test_funnel_empty_store(self):
        """GET /funnel for an empty store should return zero counts at every stage."""
        response = client.get(f"/stores/{STORE_ID}/funnel")
        assert response.status_code == 200
        data = response.json()
        assert data["store_id"] == STORE_ID
        funnel = data["funnel"]
        assert len(funnel) == 4
        for step in funnel:
            assert step["count"] == 0

    def test_heatmap_empty_store(self):
        """GET /heatmap for an empty store should return empty zones, not crash."""
        response = client.get(f"/stores/{STORE_ID}/heatmap")
        assert response.status_code == 200
        data = response.json()
        assert data["zones"] == []
        assert data["data_confidence"] == "LOW"

    def test_anomalies_empty_store(self):
        """GET /anomalies for an empty store should return empty list."""
        response = client.get(f"/stores/{STORE_ID}/anomalies")
        assert response.status_code == 200
        data = response.json()
        assert data["active_anomalies"] == []

    def test_health_no_stores(self):
        """GET /health when no events exist should still return healthy."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


# ─── Edge Case: All-Staff Clip ──────────────────────────────────────

class TestAllStaffClip:
    """When all detections are is_staff=True, customer metrics must show 0."""

    def test_all_staff_metrics_show_zero_visitors(self):
        """Ingest only staff events — unique visitors must be 0."""
        events = [
            _make_event("ENTRY", "VIS_staff_1", is_staff=True),
            _make_event("ZONE_ENTER", "VIS_staff_1", zone_id="SKINCARE", is_staff=True, session_seq=2),
            _make_event("ZONE_EXIT", "VIS_staff_1", zone_id="SKINCARE", dwell_ms=5000, is_staff=True, session_seq=3),
            _make_event("ENTRY", "VIS_staff_2", is_staff=True),
            _make_event("ZONE_ENTER", "VIS_staff_2", zone_id="BILLING", is_staff=True, session_seq=2),
        ]

        resp = client.post("/events/ingest", json=events)
        assert resp.status_code == 200

        metrics_resp = client.get(f"/stores/{STORE_ID}/metrics")
        data = metrics_resp.json()
        assert data["unique_visitors_today"] == 0
        assert data["conversion_rate"] == 0.0

    def test_all_staff_funnel_shows_zero(self):
        """Staff should be excluded from funnel counts entirely."""
        events = [
            _make_event("ENTRY", "VIS_staff_1", is_staff=True),
            _make_event("ZONE_ENTER", "VIS_staff_1", zone_id="SKINCARE", is_staff=True, session_seq=2),
            _make_event("BILLING_QUEUE_JOIN", "VIS_staff_1", zone_id="BILLING", is_staff=True, queue_depth=1, session_seq=3),
        ]

        client.post("/events/ingest", json=events)

        funnel_resp = client.get(f"/stores/{STORE_ID}/funnel")
        funnel = funnel_resp.json()["funnel"]
        for step in funnel:
            assert step["count"] == 0


# ─── Edge Case: Zero Purchases ──────────────────────────────────────

class TestZeroPurchases:
    """Visitors enter and browse but no one reaches billing — conversion must be 0."""

    def test_zero_purchase_conversion_rate(self):
        """With visitors but zero billing exits, conversion rate must be 0, no division error."""
        events = [
            _make_event("ENTRY", "VIS_a"),
            _make_event("ZONE_ENTER", "VIS_a", zone_id="SKINCARE", session_seq=2),
            _make_event("ZONE_EXIT", "VIS_a", zone_id="SKINCARE", dwell_ms=10000, session_seq=3),
            _make_event("ENTRY", "VIS_b"),
            _make_event("ZONE_ENTER", "VIS_b", zone_id="SKINCARE", session_seq=2),
            _make_event("ZONE_EXIT", "VIS_b", zone_id="SKINCARE", dwell_ms=8000, session_seq=3),
        ]

        client.post("/events/ingest", json=events)

        metrics_resp = client.get(f"/stores/{STORE_ID}/metrics")
        data = metrics_resp.json()
        assert data["unique_visitors_today"] == 2
        assert data["conversion_rate"] == 0.0
        # No division by zero errors
        assert data["abandonment_rate"] == 0.0


# ─── Edge Case: Re-entry Should Not Double-Count in Funnel ──────────

class TestReentryFunnel:
    """A visitor who exits and re-enters should not inflate funnel counts."""

    def test_reentry_does_not_double_count_entry(self):
        """REENTRY event with same visitor_id should not create duplicate in funnel."""
        events = [
            _make_event("ENTRY", "VIS_reenter", session_seq=1),
            _make_event("ZONE_ENTER", "VIS_reenter", zone_id="SKINCARE", session_seq=2),
            _make_event("ZONE_EXIT", "VIS_reenter", zone_id="SKINCARE", dwell_ms=5000, session_seq=3),
            _make_event("EXIT", "VIS_reenter", session_seq=4),
            _make_event("REENTRY", "VIS_reenter", session_seq=5),
            _make_event("ZONE_ENTER", "VIS_reenter", zone_id="BILLING", session_seq=6),
        ]

        client.post("/events/ingest", json=events)

        funnel_resp = client.get(f"/stores/{STORE_ID}/funnel")
        funnel = funnel_resp.json()["funnel"]

        # "Entered" step should count VIS_reenter only once (COUNT DISTINCT visitor_id)
        entered_step = funnel[0]
        assert entered_step["count"] == 1  # Not 2


# ─── Edge Case: Partial Success on Malformed Events ─────────────────

class TestPartialSuccessIngestion:
    """Malformed events should not prevent valid events from being ingested."""

    def test_partial_success_returns_errors(self):
        """Mix of valid and invalid events: valid ones ingested, errors reported."""
        valid_event = _make_event("ENTRY", "VIS_valid")
        malformed_event = {
            "event_id": "bad-event",
            "store_id": STORE_ID,
            # Missing required fields: camera_id, visitor_id, event_type, timestamp, etc.
        }

        resp = client.post("/events/ingest", json=[valid_event, malformed_event])
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "partial_success"
        assert data["accepted"] == 1
        assert data["inserted"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["index"] == 1

    def test_all_valid_events_returns_success(self):
        """All valid events should return status=success with no errors."""
        events = [
            _make_event("ENTRY", "VIS_ok_1"),
            _make_event("ENTRY", "VIS_ok_2"),
        ]
        resp = client.post("/events/ingest", json=events)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["accepted"] == 2
        assert data["errors"] == []

    def test_idempotent_ingestion(self):
        """Posting the same event_id twice should insert only once."""
        event = _make_event("ENTRY", "VIS_idem", event_id="fixed-id-12345")
        
        resp1 = client.post("/events/ingest", json=[event])
        assert resp1.json()["inserted"] == 1

        resp2 = client.post("/events/ingest", json=[event])
        assert resp2.json()["inserted"] == 0  # Duplicate — not re-inserted
        assert resp2.json()["accepted"] == 1  # Still accepted (valid schema)
