import argparse
import logging
import cv2
import numpy as np
from datetime import datetime, timezone, timedelta
import time

from src.cv_layer.tracker import Tracker, ReIDManager
from src.cv_layer.zone_mapper import ZoneManager
from src.cv_layer.extractor import EventExtractor
from src.streaming.streamer import EventStreamer
from src.streaming.pos_correlator import POSCorrelator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("pipeline_runner")

def run_real_pipeline(args):
    logger.info("Initializing components...")
    
    # 1. Initialize POS Correlator with real transaction CSV
    pos_correlator = POSCorrelator()
    if args.pos_csv:
        logger.info(f"Loading POS transactions from {args.pos_csv}...")
        pos_correlator.load_transactions(args.pos_csv)
        logger.info(f"Loaded {len(pos_correlator.transactions)} transactions.")
        
    # 2. Initialize CV & Ingestion Pipeline modules
    reid_manager = ReIDManager()
    zone_manager = ZoneManager(args.layout, args.camera_id)
    logger.info(f"Loaded {len(zone_manager.zones)} zones for camera {args.camera_id} from {args.layout}.")
    
    tracker = Tracker() # Default is yolov8n.pt
    
    extractor = EventExtractor(
        store_id=args.store_id,
        camera_id=args.camera_id,
        reid_manager=reid_manager,
        zone_manager=zone_manager,
        pos_correlator=pos_correlator
    )
    
    streamer = EventStreamer(api_url=args.api_url, batch_size=args.batch_size)
    
    # 3. Parse Base Time
    if args.base_time:
        try:
            base_time = datetime.fromisoformat(args.base_time.replace('Z', '+00:00'))
        except ValueError:
            logger.error(f"Invalid base-time format: {args.base_time}. Must be ISO 8601 (e.g. 2026-04-10T16:50:00Z).")
            return
    else:
        # Default to standard start time of the transactions (e.g. 2026-04-10 16:45:00 UTC)
        base_time = datetime(2026, 4, 10, 16, 45, 0, tzinfo=timezone.utc)
        logger.info(f"No --base-time provided. Defaulting to transaction start time: {base_time.isoformat()}")

    # 4. Open Video Stream
    logger.info(f"Opening video clip: {args.video}...")
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        logger.error(f"Could not open video file: {args.video}")
        return
        
    original_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_size = (width, height)
    logger.info(f"Video metadata - FPS: {original_fps:.2f}, Total Frames: {total_frames} | Dimensions: {width}x{height}")
    
    # Sampling configuration
    frame_interval = int(original_fps / args.sample_fps) if original_fps > args.sample_fps else 1
    logger.info(f"Running tracking at {args.sample_fps} FPS (sampling 1 frame every {frame_interval} video frames)")
    
    frame_idx = 0
    processed_count = 0
    start_wall_time = time.time()
    
    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                logger.info("Video playback completed or end of file reached.")
                break
                
            # Skip frames to match target FPS
            if frame_idx % frame_interval != 0:
                frame_idx += 1
                continue
                
            # Calculate timeline timestamp based on frame offset
            time_offset = timedelta(seconds=frame_idx / original_fps)
            frame_time = base_time + time_offset
            
            # Step A: Perform YOLO Detection & ByteTrack
            detections = tracker.process_frame(frame)
            
            # Step B: Map coordinates to Zones & Extract behavioural events
            events = extractor.process_detections(detections, frame_time, frame_size=frame_size)
            
            # Step C: Queue generated events for streaming
            if events:
                logger.info(f"Frame {frame_idx}: Extracted {len(events)} events (Time: {frame_time.isoformat()})")
                for ev in events:
                    logger.info(f"  - Event: {ev.event_type.value} | Visitor: {ev.visitor_id} | Zone: {ev.zone_id}")
                streamer.add_events(events)
                
            processed_count += 1
            frame_idx += 1
            
            # Visual Preview (optional)
            if args.show_preview:
                try:
                    annotated_frame = frame.copy()
                    
                    # Draw Zone polygons
                    for zone_id, polygon in zone_manager.zones.items():
                        pts = np.array(polygon.exterior.coords, np.int32)
                        cv2.polylines(annotated_frame, [pts], isClosed=True, color=(0, 255, 0), thickness=2)
                        cv2.putText(annotated_frame, zone_id, tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        
                    # Draw tracked person detections
                    if len(detections) > 0:
                        for i in range(len(detections)):
                            box = detections.xyxy[i].astype(int)
                            track_id = detections.tracker_id[i] if detections.tracker_id is not None else "N/A"
                            cv2.rectangle(annotated_frame, (box[0], box[1]), (box[2], box[3]), (255, 0, 0), 2)
                            cv2.putText(annotated_frame, f"ID: {track_id}", (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                            
                    # Display preview
                    cv2.imshow("Purplle CCTV Live Tracking Preview", annotated_frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        logger.info("Preview display closed by user.")
                        break
                except cv2.error as e:
                    logger.warning(f"Unable to show visual preview (running in headless console?): {e}")
                    args.show_preview = False
            
            # Print periodic logs
            if processed_count % 50 == 0:
                elapsed = time.time() - start_wall_time
                fps_rate = processed_count / elapsed
                logger.info(f"Progress: Processed {processed_count} frames | Frame Time: {frame_time.strftime('%H:%M:%S')} | Processing Rate: {fps_rate:.2f} FPS")
                
            if args.max_frames and processed_count >= args.max_frames:
                logger.info(f"Reached user-configured frame limit of {args.max_frames}. Stopping.")
                break
                
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Exiting gracefully...")
    finally:
        # Flush any remaining events
        logger.info("Flushing final events buffer...")
        streamer.flush()
        cap.release()
        if args.show_preview:
            cv2.destroyAllWindows()
        logger.info("Pipeline processing runner terminated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purplle Store Intelligence Video Pipeline Runner")
    parser.add_argument("--video", type=str, required=True, help="Path to raw CCTV video (.mp4) file")
    parser.add_argument("--store-id", type=str, default="purplle_brigade_road", help="Store Identifier")
    parser.add_argument("--camera-id", type=str, default="cam_1", help="Camera View Identifier")
    parser.add_argument("--layout", type=str, default="store_layout.json", help="Path to store layout configuration JSON")
    parser.add_argument("--pos-csv", type=str, default="", help="Path to the real POS transactions CSV file")
    parser.add_argument("--api-url", type=str, default="http://localhost:8000", help="URL base of store intelligence API")
    parser.add_argument("--base-time", type=str, default="", help="ISO 8601 base timestamp for start of video clip (e.g. 2026-04-10T16:45:00Z)")
    parser.add_argument("--sample-fps", type=int, default=3, help="Processing frame rate (1-5 FPS recommended)")
    parser.add_argument("--batch-size", type=int, default=5, help="Event batch stream size")
    parser.add_argument("--max-frames", type=int, default=0, help="Maximum number of frames to process (0 = infinite)")
    parser.add_argument("--show-preview", action="store_true", help="Display visual cv2 debug tracking window")
    
    args = parser.parse_args()
    run_real_pipeline(args)
