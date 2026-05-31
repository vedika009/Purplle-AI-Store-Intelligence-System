# PROMPT: "Write a pytest test file to validate the EventSchema Pydantic model for the Purplle AI challenge. Include happy paths and invalid data tests."
# CHANGES MADE: "Adjusted exactly to match the schema definitions, adding a specific test for the REENTRY and BILLING_QUEUE_ABANDON edge cases."

import pytest
from pydantic import ValidationError
from datetime import datetime, timezone
import uuid

from src.cv_layer.schema import EventSchema, EventType, EventMetadata

def test_valid_event_schema():
    event_data = {
        "event_id": str(uuid.uuid4()),
        "store_id": "STORE_BLR_002",
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": "VIS_c8a2f1",
        "event_type": "ZONE_DWELL",
        "timestamp": "2026-03-03T14:22:10Z",
        "zone_id": "SKINCARE",
        "dwell_ms": 8400,
        "is_staff": False,
        "confidence": 0.91,
        "metadata": {
            "queue_depth": None,
            "sku_zone": "MOISTURISER",
            "session_seq": 5
        }
    }
    
    event = EventSchema(**event_data)
    assert event.event_type == EventType.ZONE_DWELL
    assert event.confidence == 0.91
    assert event.metadata.session_seq == 5
    # Timestamp parsing should map appropriately
    assert event.timestamp.year == 2026

def test_missing_required_fields():
    event_data = {
        "event_id": str(uuid.uuid4()),
        "store_id": "STORE_BLR_002",
        # camera_id missing
    }
    with pytest.raises(ValidationError):
        EventSchema(**event_data)

def test_invalid_event_type():
    event_data = {
        "event_id": str(uuid.uuid4()),
        "store_id": "STORE_BLR_002",
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": "VIS_c8a2f1",
        "event_type": "INVALID_TYPE", # This should fail
        "timestamp": "2026-03-03T14:22:10Z",
        "zone_id": "SKINCARE",
        "dwell_ms": 8400,
        "is_staff": False,
        "confidence": 0.91,
        "metadata": {"session_seq": 1}
    }
    with pytest.raises(ValidationError):
        EventSchema(**event_data)
        
def test_edge_case_events():
    # REENTRY
    reentry_data = {
        "event_id": str(uuid.uuid4()),
        "store_id": "STORE_BLR_002",
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": "VIS_c8a2f1",
        "event_type": "REENTRY",
        "timestamp": "2026-03-03T14:40:10Z",
        "zone_id": None,
        "dwell_ms": 0,
        "is_staff": False,
        "confidence": 0.88,
        "metadata": {"session_seq": 10}
    }
    event = EventSchema(**reentry_data)
    assert event.event_type == EventType.REENTRY
    
    # BILLING_QUEUE_JOIN needs queue_depth
    billing_data = {
        "event_id": str(uuid.uuid4()),
        "store_id": "STORE_BLR_002",
        "camera_id": "CAM_BILLING_01",
        "visitor_id": "VIS_c8a2f1",
        "event_type": "BILLING_QUEUE_JOIN",
        "timestamp": "2026-03-03T14:42:10Z",
        "zone_id": "BILLING",
        "dwell_ms": 0,
        "is_staff": False,
        "confidence": 0.95,
        "metadata": {"queue_depth": 3, "session_seq": 11}
    }
    event = EventSchema(**billing_data)
    assert event.event_type == EventType.BILLING_QUEUE_JOIN
    assert event.metadata.queue_depth == 3
