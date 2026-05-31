import cv2
import supervision as sv
from ultralytics import YOLO
import numpy as np
from typing import Dict, List, Any, Optional

class Tracker:
    def __init__(self, model_path: str = "yolov8n.pt", confidence_threshold: float = 0.5):
        """
        Initializes the YOLO model and ByteTrack.
        Using YOLOv8 nano by default for speed, tracking 'person' class (class_id=0).
        """
        self.model = YOLO(model_path)
        self.tracker = sv.ByteTrack()
        self.confidence_threshold = confidence_threshold
        
    def process_frame(self, frame: np.ndarray) -> sv.Detections:
        """
        Runs inference and tracking on a single frame.
        """
        # Run YOLO inference
        results = self.model(frame, verbose=False)[0]
        
        # Convert to supervision detections
        detections = sv.Detections.from_ultralytics(results)
        
        # Filter for 'person' class only (class_id == 0) and apply confidence threshold
        person_mask = (detections.class_id == 0) & (detections.confidence >= self.confidence_threshold)
        detections = detections[person_mask]
        
        # Update tracker
        tracked_detections = self.tracker.update_with_detections(detections=detections)
        
        return tracked_detections

class ReIDManager:
    """
    Manages the mapping between short-lived track_ids and long-lived visitor_ids.
    Also handles the 'is_staff' classification logic.
    """
    def __init__(self):
        self.track_to_visitor: Dict[int, str] = {}
        self.staff_tracks = set()
        
    def get_visitor_id(self, track_id: int) -> str:
        # In a real scenario, this would use deep sort / OSNet to check if a new track_id
        # visually matches an old visitor_id (Re-ID for re-entry).
        # For now, we simulate by mapping 1:1, but the architecture supports complex logic here.
        import uuid
        if track_id not in self.track_to_visitor:
            self.track_to_visitor[track_id] = f"VIS_{str(uuid.uuid4())[:8]}"
        return self.track_to_visitor[track_id]
        
    def mark_staff(self, track_id: int):
        self.staff_tracks.add(track_id)
        
    def is_staff(self, track_id: int) -> bool:
        return track_id in self.staff_tracks
