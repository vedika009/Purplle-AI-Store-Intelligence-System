# PROMPT: "Write pytest cases for the Tracker, ReIDManager, and ZoneManager in the computer vision pipeline. Ensure mocking for YOLO to prevent large downloads during tests."
# CHANGES MADE: "Adjusted to mock ultralytics YOLO model so CI/CD doesn't try to download weights. Added explicit layout JSON writing for the ZoneManager test."

import pytest
import numpy as np
import json
from unittest.mock import MagicMock, patch

from src.cv_layer.tracker import Tracker, ReIDManager
from src.cv_layer.zone_mapper import ZoneManager

@patch("src.cv_layer.tracker.YOLO")
def test_tracker_initialization(mock_yolo):
    tracker = Tracker(model_path="mock.pt", confidence_threshold=0.6)
    assert tracker.confidence_threshold == 0.6
    mock_yolo.assert_called_once_with("mock.pt")

def test_reid_manager():
    manager = ReIDManager()
    
    # Test new ID assignment
    vis1 = manager.get_visitor_id(1)
    assert vis1.startswith("VIS_")
    
    # Test consistent ID return
    assert manager.get_visitor_id(1) == vis1
    
    # Test different track ID gets different visitor ID
    vis2 = manager.get_visitor_id(2)
    assert vis1 != vis2
    
    # Test staff marking
    assert manager.is_staff(1) is False
    manager.mark_staff(1)
    assert manager.is_staff(1) is True

def test_zone_manager(tmp_path):
    layout_data = {
        "CAM_ENTRY_01": {
            "SKINCARE": [[0, 0], [10, 0], [10, 10], [0, 10]]
        }
    }
    
    layout_file = tmp_path / "store_layout.json"
    layout_file.write_text(json.dumps(layout_data))
    
    manager = ZoneManager(str(layout_file), "CAM_ENTRY_01")
    
    # Inside the zone (SKINCARE box is 0,0 to 10,10)
    assert manager.get_zone(5, 5) == "SKINCARE"
    
    # On the edge
    assert manager.get_zone(0, 5) == "SKINCARE"
    
    # Outside the zone
    assert manager.get_zone(15, 15) is None
