import cv2
import time
import logging
import threading
from typing import Tuple

from .reader import VideoReader
from .writer import ObjectStoreWriter

logger = logging.getLogger(__name__)

class FrameProcessor:
    def __init__(self, reader: VideoReader, writer: ObjectStoreWriter, target_fps: int, resolution: Tuple[int, int]):
        self.reader = reader
        self.writer = writer
        self.target_fps = target_fps
        self.resolution = resolution
        self.running = False
        self._thread = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def _process_loop(self):
        frame_interval = 1.0 / self.target_fps
        while self.running and self.reader.running:
            start_time = time.time()
            
            frame = self.reader.read_latest()
            if frame is not None:
                # 1. Resize to target resolution (e.g. 640x640 for YOLO)
                processed = cv2.resize(frame, self.resolution)
                
                # 2. Normalize/Color
                # Note: We keep it in BGR because OpenCV's imwrite expects BGR to produce a correct JPEG.
                # Phase 2 (CV Layer) will read the JPEG and handle RGB conversion for inference.
                
                # 3. Denoise (Lightweight Gaussian Blur to reduce artifacts)
                processed = cv2.GaussianBlur(processed, (3, 3), 0)
                
                # Write to object store simulation
                self.writer.save_frame(self.reader.camera_id, processed)

            # Sleep to maintain the configured target FPS
            elapsed = time.time() - start_time
            sleep_time = max(0.0, frame_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self):
        self.running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join()
