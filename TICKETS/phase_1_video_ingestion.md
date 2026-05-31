# Phase 1: Video Ingestion & Frame Pipeline

## Goal
Implement reliable, low-latency frame extraction from RTSP/video sources for footfall analytics.

## Tasks
- [x] Create ingestion service configuration schema (support for N cameras).
- [x] Implement RTSP stream reader (using OpenCV or FFmpeg).
- [x] Build frame sampler (configurable 1–5 FPS rate).
- [x] Implement pre-processing (resize 640x640, normalize, denoise).
- [x] Develop object store writer (key structure: `{store_id}/{camera_id}/{timestamp}.jpg`).

## Testing Requirements
- [x] Add `# PROMPT:` and `# CHANGES MADE:` blocks at the top of all test files (Part D AI Engineering requirement).

## Documentation
- [x] Document reasoning for 1-5 FPS sampling rate and its impact on performance/accuracy.
