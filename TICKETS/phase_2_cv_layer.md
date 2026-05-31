# Phase 2: Computer Vision Layer

## Goal
Extract semantic events from video frames using detection and tracking.

## Tasks
- [ ] Set up YOLOv8 (nano/small) for person detection.
- [ ] Implement multi-object tracker (ByteTrack/BoT-SORT) for track ID consistency.
- [ ] Create zone mapper (Polygon ROI definitions via JSON).
- [ ] Implement point-in-polygon logic using `shapely`.
- [ ] Develop event extractor to emit structured events:
  - `PersonEntered(zone, track_id, timestamp)`
  - `PersonExited(zone, track_id, timestamp, dwell_seconds)`
  - `QueueDepth(zone, count, timestamp)`
  - `CrowdAlert(zone, density, timestamp)`

## Documentation
- [ ] Document trade-off decision: Zone-based spatial logic vs. pose/action recognition.
