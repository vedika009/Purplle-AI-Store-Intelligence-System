import cv2
import threading
import time
import logging

logger = logging.getLogger(__name__)

class VideoReader:
    def __init__(self, source: str, camera_id: str):
        self.source = source
        self.camera_id = camera_id
        self.cap = cv2.VideoCapture(self.source)
        self.latest_frame = None
        self.running = False
        self._thread = None
        self._lock = threading.Lock()

        if not self.cap.isOpened():
            logger.error(f"Failed to open source {self.source} for camera {self.camera_id}")
            raise ValueError(f"Unable to open video source: {self.source}")

        # Try to get native FPS, fallback to 30 if unavailable
        self.native_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if not self.native_fps or self.native_fps <= 0:
            self.native_fps = 30.0

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._update, daemon=True)
        self._thread.start()

    def _update(self):
        # Simulate real-time streaming delay if reading from a local file
        is_file = not (self.source.startswith("rtsp://") or self.source.startswith("http://") or self.source.startswith("https://"))
        frame_delay = 1.0 / self.native_fps if is_file else 0.0

        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self._lock:
                    self.latest_frame = frame
            else:
                logger.info(f"Stream ended or no frame received for {self.camera_id}.")
                self.running = False
                break
            
            if is_file:
                time.sleep(frame_delay)
            else:
                time.sleep(0.001)  # small yield for live streams

    def read_latest(self):
        with self._lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy()
            return None

    def stop(self):
        self.running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join()
        self.cap.release()
