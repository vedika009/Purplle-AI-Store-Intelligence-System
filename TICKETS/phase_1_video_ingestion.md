# Phase 1: Video Ingestion & Frame Pipeline

## Goal
Implement reliable, low-latency frame extraction from RTSP/video sources for footfall analytics.

## Tasks
- [ ] Create ingestion service configuration schema (support for N cameras).
- [ ] Implement RTSP stream reader (using OpenCV or FFmpeg).
- [ ] Build frame sampler (configurable 1–5 FPS rate).
- [ ] Implement pre-processing (resize 640x640, normalize, denoise).
- [ ] Develop object store writer (key structure: `{store_id}/{camera_id}/{timestamp}.jpg`).

## Documentation
- [ ] Document reasoning for 1-5 FPS sampling rate and its impact on performance/accuracy.
