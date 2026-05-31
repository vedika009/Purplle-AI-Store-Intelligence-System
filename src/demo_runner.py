import time
import argparse
import logging
from datetime import datetime, timezone
import numpy as np
import supervision as sv

from src.cv_layer.tracker import Tracker, ReIDManager
from src.cv_layer.zone_mapper import ZoneManager
from src.cv_layer.extractor import EventExtractor
from src.streaming.streamer import EventStreamer
from src.streaming.pos_correlator import POSCorrelator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("demo_runner")

def simulate_detections(frame_idx: int) -> sv.Detections:
    """
    Simulates people moving through the store over 60 frames.
    Person 1 (track 1): Enters -> Browses (SKINCARE) -> Queues (BILLING) -> Checks out
    Person 2 (track 2): Enters -> Browses (SKINCARE) -> Leaves (Drop-off)
    Person 3-8 (track 3-8): Queue Spike in BILLING
    """
    detections_list = []
    
    # Person 1: Conversion journey
    if 0 <= frame_idx < 10:
        # Just entered, no zone yet (or ENTRY_DOOR)
        detections_list.append([50, 50, 100, 90, 0.9, 0, 1]) # center is ~75, bottom is 90 -> ENTRY_DOOR
    elif 10 <= frame_idx < 30:
        # In SKINCARE (center x=75, bottom y=250)
        detections_list.append([50, 200, 100, 250, 0.9, 0, 1])
    elif 30 <= frame_idx < 50:
        # In BILLING (center x=300, bottom y=200)
        detections_list.append([250, 100, 350, 200, 0.9, 0, 1])
        
    # Person 2: Drop journey
    if 5 <= frame_idx < 25:
        # In SKINCARE
        detections_list.append([100, 200, 150, 300, 0.9, 0, 2])
        
    # Queue spike simulation (Anomalous queue)
    if 35 <= frame_idx < 45:
        for i in range(3, 8):
            # All in BILLING
            detections_list.append([200+i*10, 100+i*5, 250+i*10, 150+i*5, 0.9, 0, i])
            
    # Dead zone simulation: The right side of the store (e.g., beyond x=400) has no detections
            
    if not detections_list:
        return sv.Detections.empty()
        
    data = np.array(detections_list)
    return sv.Detections(
        xyxy=data[:, :4],
        confidence=data[:, 4],
        class_id=data[:, 5].astype(int),
        tracker_id=data[:, 6].astype(int)
    )

def run_pipeline(simulate: bool):
    logger.info("Initializing pipeline components...")
    reid_manager = ReIDManager()
    zone_manager = ZoneManager("store_layout.json", "cam_1")
    pos_correlator = POSCorrelator()
    extractor = EventExtractor("purplle_brigade_road", "cam_1", reid_manager, zone_manager, pos_correlator)
    streamer = EventStreamer(api_url="http://localhost:8000", batch_size=2) # Small batch for fast live updates
    
    if not simulate:
        logger.info("Running in normal mode, expecting real video feed or RTSP stream. (Not implemented in this demo script - use main.py for real feeds. Switching to simulate)")
        simulate = True

    logger.info("Starting pipeline simulation...")

    frame_idx = 0
    while True:
        try:
            now = datetime.now(timezone.utc)
            
            detections = simulate_detections(frame_idx)
            
            # Inject a POS transaction right before Person 1 exits billing (frame 49)
            if frame_idx == 49:
                logger.info("Injecting simulated POS transaction for correlation")
                pos_correlator.transactions.append({
                    "transaction_id": f"sim_tx_{frame_idx}",
                    "store_id": "purplle_brigade_road",
                    "timestamp": now,
                    "amount": 1500
                })
                
            events = extractor.process_detections(detections, now)
            
            if events:
                logger.debug(f"Extracted {len(events)} events at frame {frame_idx}")
                streamer.add_events(events)
            
            # Periodic flush
            if frame_idx % 5 == 0:
                streamer.flush()
                
            frame_idx += 1
            
            # Loop simulation
            if frame_idx > 60:
                logger.info("Simulation cycle complete. Resetting state for continuous loop.")
                frame_idx = 0 
                pos_correlator.transactions = []
                # Clear states to simulate a new day/session without infinitely growing track memory
                extractor.visitor_states.clear()
                reid_manager.track_to_visitor.clear()
                
            time.sleep(1) # 1 FPS simulation for visible dashboard updates
            
        except KeyboardInterrupt:
            logger.info("Stopping runner...")
            streamer.flush()
            break
        except Exception as e:
            logger.error(f"Error in pipeline: {e}")
            time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purplle Store Intelligence Demo Runner")
    parser.add_argument("--simulate", action="store_true", help="Run with simulated tracking data", default=True)
    args = parser.parse_args()
    
    run_pipeline(args.simulate)
