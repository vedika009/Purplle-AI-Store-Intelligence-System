# PROMPT: "Write pytest test cases for the config parsing and image saving writer in a video ingestion pipeline using cv2 and numpy."
# CHANGES MADE: "Adjusted dummy frame sizes and specific path checking to match our application's exact output schema requirements."

import os
import cv2
import numpy as np

from src.ingestion.writer import ObjectStoreWriter
from src.ingestion.config import AppConfig

def test_config_parsing(tmp_path):
    yaml_content = """
store_id: "test_store"
ingestion:
  output_dir: "./data/processed"
  target_resolution: [320, 320]
cameras:
  - camera_id: "cam_1"
    source: "rtsp://localhost/stream"
    target_fps: 5
    enabled: true
"""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(yaml_content)
    
    config = AppConfig.load_from_yaml(str(config_file))
    
    assert config.store_id == "test_store"
    assert config.ingestion.target_resolution == (320, 320)
    assert len(config.cameras) == 1
    assert config.cameras[0].target_fps == 5
    assert config.cameras[0].source == "rtsp://localhost/stream"

def test_writer_creates_files(tmp_path):
    # Create a dummy frame (100x100 BGR)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    
    writer = ObjectStoreWriter(store_id="test_store", base_dir=str(tmp_path))
    
    path = writer.save_frame("cam_test", frame)
    
    # Assert file was created with correct structure
    assert os.path.exists(path)
    assert "test_store" in path
    assert "cam_test" in path
    assert path.endswith(".jpg")
    
    # Check if we can read it back
    saved_frame = cv2.imread(path)
    assert saved_frame is not None
    assert saved_frame.shape == (100, 100, 3)
