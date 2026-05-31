# PROMPT: Implement tests for the AnomalyDetector class to cover queue spike, dead zone, and conversion drop detection scenarios.
# CHANGES MADE: Created `tests/test_anomaly.py` covering event processing, dead zone timeout checks, and conversion drop threshold calculations.

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from src.anomaly.detector import AnomalyDetector
from src.anomaly.schema import AnomalyType, Severity
from src.cv_layer.schema import EventSchema, EventType, EventMetadata

@pytest.fixture
def detector():
    return AnomalyDetector(queue_threshold=5, dead_zone_minutes=30)

@pytest.fixture
def base_time():
    return datetime.now(timezone.utc)

def create_event(event_type: EventType, zone_id: str = None, queue_depth: int = 0, timestamp: datetime = None) -> EventSchema:
    return EventSchema(
        event_id=str(uuid.uuid4()),
        store_id="store_1",
        camera_id="cam_1",
        visitor_id="visitor_1",
        event_type=event_type,
        timestamp=timestamp or datetime.now(timezone.utc),
        confidence=0.9,
        zone_id=zone_id,
        metadata=EventMetadata(session_seq=1, queue_depth=queue_depth)
    )

def test_queue_spike(detector):
    # Under threshold
    event = create_event(EventType.BILLING_QUEUE_JOIN, zone_id="BILLING", queue_depth=5)
    anomaly = detector.process_event(event)
    assert anomaly is None
    
    # Over threshold (WARN)
    event2 = create_event(EventType.BILLING_QUEUE_JOIN, zone_id="BILLING", queue_depth=6)
    anomaly2 = detector.process_event(event2)
    assert anomaly2 is not None
    assert anomaly2.anomaly_type == AnomalyType.QUEUE_SPIKE
    assert anomaly2.severity == Severity.WARN
    
    # Over threshold (CRITICAL)
    event3 = create_event(EventType.BILLING_QUEUE_JOIN, zone_id="BILLING", queue_depth=12)
    anomaly3 = detector.process_event(event3)
    assert anomaly3.severity == Severity.CRITICAL

def test_dead_zone(detector, base_time):
    # Setup: Someone seen in MAKEUP zone
    event = create_event(EventType.ZONE_ENTER, zone_id="MAKEUP", timestamp=base_time - timedelta(minutes=45))
    detector.process_event(event)
    
    # Check 45 mins later -> should be dead zone
    anomalies = detector.check_dead_zones("store_1", base_time, ["MAKEUP", "SKINCARE"])
    assert len(anomalies) == 1
    assert anomalies[0].zone_id == "MAKEUP"
    assert anomalies[0].anomaly_type == AnomalyType.DEAD_ZONE
    assert anomalies[0].severity == Severity.INFO # < 60 mins
    
    # Check 65 mins later -> WARN
    anomalies_warn = detector.check_dead_zones("store_1", base_time + timedelta(minutes=20), ["MAKEUP"])
    assert anomalies_warn[0].severity == Severity.WARN

def test_conversion_drop(detector, base_time):
    # No drop
    anomaly = detector.check_conversion_drop("store_1", base_time, current_cr=0.15, avg_7d_cr=0.15)
    assert anomaly is None
    
    # 25% drop (0.20 to 0.15)
    anomaly_warn = detector.check_conversion_drop("store_1", base_time, current_cr=0.15, avg_7d_cr=0.20)
    assert anomaly_warn is not None
    assert anomaly_warn.anomaly_type == AnomalyType.CONVERSION_DROP
    assert anomaly_warn.severity == Severity.WARN
    
    # 50% drop (0.20 to 0.10)
    anomaly_crit = detector.check_conversion_drop("store_1", base_time, current_cr=0.10, avg_7d_cr=0.20)
    assert anomaly_crit.severity == Severity.CRITICAL
    
def test_zero_avg_cr(detector, base_time):
    anomaly = detector.check_conversion_drop("store_1", base_time, current_cr=0.0, avg_7d_cr=0.0)
    assert anomaly is None
