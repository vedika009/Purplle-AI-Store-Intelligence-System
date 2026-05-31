import time
import logging
from typing import List

from .config import AppConfig
from .reader import VideoReader
from .writer import ObjectStoreWriter
from .processor import FrameProcessor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

def main(config_path: str):
    logger.info(f"Loading configuration from {config_path}")
    config = AppConfig.load_from_yaml(config_path)
    
    writer = ObjectStoreWriter(store_id=config.store_id, base_dir=config.ingestion.output_dir)
    
    readers: List[VideoReader] = []
    processors: List[FrameProcessor] = []
    
    for cam_config in config.cameras:
        if not cam_config.enabled:
            logger.info(f"Skipping disabled camera: {cam_config.camera_id}")
            continue
            
        logger.info(f"Starting ingestion pipeline for camera: {cam_config.camera_id} at {cam_config.target_fps} FPS")
        
        try:
            reader = VideoReader(source=cam_config.source, camera_id=cam_config.camera_id)
            processor = FrameProcessor(
                reader=reader,
                writer=writer,
                target_fps=cam_config.target_fps,
                resolution=tuple(config.ingestion.target_resolution)
            )
            
            readers.append(reader)
            processors.append(processor)
            
            reader.start()
            processor.start()
        except Exception as e:
            logger.error(f"Failed to initialize pipeline for {cam_config.camera_id}: {e}")

    try:
        # Keep main thread alive while workers process the video feeds
        while True:
            # If all readers have stopped (e.g. video files ended), shut down gracefully
            if readers and all(not r.running for r in readers):
                logger.info("All video streams have ended. Shutting down.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down gracefully.")
    finally:
        logger.info("Stopping all processors and readers...")
        for p in processors:
            p.stop()
        for r in readers:
            r.stop()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    import sys
    config_file = sys.argv[1] if len(sys.argv) > 1 else "config/cameras.yaml"
    main(config_file)
