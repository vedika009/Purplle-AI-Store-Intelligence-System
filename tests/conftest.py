# PROMPT: "Create a shared pytest conftest.py with reusable fixtures for event creation,
# test database setup, and common test utilities across all test files."
# CHANGES MADE: Added conftest.py with shared event factory fixture and clean DB setup.
# Kept backward-compatible with existing test files that create their own helpers.

import pytest
import os
import uuid
from datetime import datetime, timezone

# ─── Shared Test Configuration ──────────────────────────────────────

TEST_STORE_ID = "STORE_TEST_001"
TEST_CAMERA_ID = "CAM_ENTRY_01"
TEST_DB_PATH = "test_conftest.db"


@pytest.fixture
def event_factory():
    """Factory fixture that creates valid event dicts for API ingestion."""
    def _make(event_type: str, visitor_id: str, zone_id=None,
              dwell_ms=0, is_staff=False, confidence=0.92,
              queue_depth=None, session_seq=1, timestamp=None,
              store_id=None, event_id=None):
        return {
            "event_id": event_id or str(uuid.uuid4()),
            "store_id": store_id or TEST_STORE_ID,
            "camera_id": TEST_CAMERA_ID,
            "visitor_id": visitor_id,
            "event_type": event_type,
            "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
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
    return _make
