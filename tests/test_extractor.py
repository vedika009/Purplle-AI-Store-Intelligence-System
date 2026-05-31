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
