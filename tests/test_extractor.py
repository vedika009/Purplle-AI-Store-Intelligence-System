# PROMPT: "Write a pytest test for the EventExtractor to simulate a detection moving from no zone into a SKINCARE zone, then to BILLING, and ensure the correct exact schema events are generated including queue_depth."
# CHANGES MADE: "Adjusted to pass `track_id` in initialization as per recent schema updates."

import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import supervision as sv

from src.cv_layer.extractor import EventExtractor
from src.cv_layer.schema import EventType
from src.cv_layer.tracker import ReIDManager
from src.cv_layer.zone_mapper import ZoneManager

def test_event_extractor_flow():
    # Setup Mocks
    reid_manager = ReIDManager()
    zone_manager = MagicMock(spec=ZoneManager)
    
    # Simulate zone layout
    def mock_get_zone(x, y):
        if 0 <= x <= 10 and 0 <= y <= 10:
            return "SKINCARE"
        elif 20 <= x <= 30 and 20 <= y <= 30:
            return "BILLING"
        return None
        
    zone_manager.get_zone.side_effect = mock_get_zone
    
    extractor = EventExtractor("STORE_01", "CAM_01", reid_manager, zone_manager)
    
    base_time = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
    
    # Frame 1: Person appears outside any zone
    xyxy1 = np.array([[100, 100, 110, 110]])
    tracker_id1 = np.array([1])
    confidence1 = np.array([0.9])
    class_id1 = np.array([0])
    
    detections1 = sv.Detections(xyxy=xyxy1, tracker_id=tracker_id1, confidence=confidence1, class_id=class_id1)
    events1 = extractor.process_detections(detections1, base_time)
    
    assert len(events1) == 1
    assert events1[0].event_type == EventType.ENTRY
    
    # Frame 2: Person moves to SKINCARE zone (+10 seconds)
    time2 = base_time + timedelta(seconds=10)
    xyxy2 = np.array([[2, 2, 8, 8]]) # Center (5,8) in SKINCARE
    detections2 = sv.Detections(xyxy=xyxy2, tracker_id=tracker_id1, confidence=confidence1, class_id=class_id1)
    
    events2 = extractor.process_detections(detections2, time2)
    assert len(events2) == 1
    assert events2[0].event_type == EventType.ZONE_ENTER
    assert events2[0].zone_id == "SKINCARE"
    
    # Frame 3: Person moves to BILLING (+20 seconds)
    time3 = time2 + timedelta(seconds=20)
    xyxy3 = np.array([[22, 22, 28, 28]]) # Center (25, 28) in BILLING
    detections3 = sv.Detections(xyxy=xyxy3, tracker_id=tracker_id1, confidence=confidence1, class_id=class_id1)
    
    events3 = extractor.process_detections(detections3, time3)
    # Should trigger ZONE_EXIT (from SKINCARE) and BILLING_QUEUE_JOIN
    assert len(events3) == 2
    
    assert events3[0].event_type == EventType.ZONE_EXIT
    assert events3[0].zone_id == "SKINCARE"
    assert events3[0].dwell_ms == 20000 # 20 seconds dwell
    
    assert events3[1].event_type == EventType.BILLING_QUEUE_JOIN
    assert events3[1].zone_id == "BILLING"
    assert events3[1].metadata.queue_depth == 1

def test_extractor_dwell_and_exit_timeout():
    reid_manager = ReIDManager()
    zone_manager = MagicMock(spec=ZoneManager)
    
    def mock_get_zone(x, y):
        return "SKINCARE"
    zone_manager.get_zone.side_effect = mock_get_zone
    
    extractor = EventExtractor("STORE_01", "CAM_01", reid_manager, zone_manager)
    base_time = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
    
    # 1. Entry & Zone Enter
    xyxy = np.array([[5, 5, 8, 8]])
    detections = sv.Detections(xyxy=xyxy, tracker_id=np.array([1]), confidence=np.array([0.9]), class_id=np.array([0]))
    
    events1 = extractor.process_detections(detections, base_time)
    assert len(events1) == 2
    assert events1[0].event_type == EventType.ENTRY
    assert events1[1].event_type == EventType.ZONE_ENTER
    
    # 2. Stay in SKINCARE for 35 seconds (triggers ZONE_DWELL at 35s)
    time2 = base_time + timedelta(seconds=35)
    events2 = extractor.process_detections(detections, time2)
    assert len(events2) == 1
    assert events2[0].event_type == EventType.ZONE_DWELL
    assert events2[0].dwell_ms == 35000
    
    # 3. Disappear (no detections in frame at +50 seconds)
    # The last seen time was time2 (10:00:35).
    # Current frame is 10:00:50 (+15 seconds later, which exceeds 10s exit_timeout).
    # This should trigger ZONE_EXIT (from SKINCARE) and EXIT at time2.
    time3 = base_time + timedelta(seconds=50)
    empty_detections = sv.Detections.empty()
    events3 = extractor.process_detections(empty_detections, time3)
    assert len(events3) == 2
    assert events3[0].event_type == EventType.ZONE_EXIT
    assert events3[0].zone_id == "SKINCARE"
    assert events3[0].dwell_ms == 35000 # Dwell up to time2
    assert events3[1].event_type == EventType.EXIT
    assert events3[1].timestamp == time2 # Exit timestamp is last_seen_time

def test_extractor_staff_marking():
    reid_manager = ReIDManager()
    zone_manager = MagicMock(spec=ZoneManager)
    
    # Setup zone manager to return STAFF_ONLY
    def mock_get_zone(x, y):
        return "STAFF_ONLY"
    zone_manager.get_zone.side_effect = mock_get_zone
    
    extractor = EventExtractor("STORE_01", "CAM_01", reid_manager, zone_manager)
    base_time = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
    
    xyxy = np.array([[5, 5, 8, 8]])
    detections = sv.Detections(xyxy=xyxy, tracker_id=np.array([1]), confidence=np.array([0.9]), class_id=np.array([0]))
    
    events = extractor.process_detections(detections, base_time)
    assert len(events) == 2
    assert events[0].event_type == EventType.ENTRY
    # Should be flagged as staff
    assert events[0].is_staff is True
    assert events[1].event_type == EventType.ZONE_ENTER
    assert events[1].is_staff is True
