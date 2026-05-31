# Phase 1: Video Ingestion FPS Reasoning

## Decision
The video ingestion pipeline downsamples incoming RTSP and video streams to **3 FPS** by default (configurable between 1-5 FPS).

## Rationale

### 1. Performance and Compute Costs
Raw CCTV footage is typically recorded at 24-30 Frames Per Second (FPS). Processing every frame through an object detection model (like YOLOv8) and a tracker (like ByteTrack) for $N$ cameras concurrently is computationally expensive and generally unnecessary for footfall and generic movement analytics.
*   **30 FPS vs 3 FPS:** By reducing the frame rate to 3 FPS, we discard 90% of the frames. This translates directly to an ~80-90% reduction in inference compute costs, allowing the system to handle more cameras per GPU/CPU node.

### 2. Analytical Accuracy (The "Sweet Spot")
*   **Too Low (1 FPS):** At 1 frame per second, fast-moving individuals might traverse significant distances between frames, or be briefly occluded and reappear far away. This causes trackers like ByteTrack to lose the identity association (ID switching), leading to overcounting.
*   **Too High (15+ FPS):** Diminishing returns. The bounding box centroid moves very slightly between frames. For retail tracking (average human walking speed is ~1.4 m/s), 30 FPS means a person moves ~4.6cm per frame, which is practically stationary for a zone-based counting system.
*   **Sweet Spot (3-5 FPS):** At 3 FPS, a person moving at 1.4 m/s travels roughly 0.46 meters (~1.5 feet) between frames. This is a large enough displacement to show clear movement but small enough that spatial tracking algorithms (IoU/ByteTrack) can easily correlate the bounding boxes and maintain persistent IDs, even across minor occlusions.

## Conclusion
A configurable rate defaulting to 3 FPS provides the optimal balance for the Purplle AI Store Intelligence System, satisfying both low-latency/low-cost operational constraints and the accuracy required for the cv layer's tracking heuristics.
