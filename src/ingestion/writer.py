import os
import cv2
import time
import logging

logger = logging.getLogger(__name__)

class ObjectStoreWriter:
    def __init__(self, store_id: str, base_dir: str):
        self.store_id = store_id
        self.base_dir = base_dir

    def save_frame(self, camera_id: str, frame) -> str:
        timestamp = int(time.time() * 1000)
        # e.g., ./data/processed_frames/purplle_brigade_road/cam_1_entrance
        cam_dir = os.path.join(self.base_dir, self.store_id, camera_id)
        os.makedirs(cam_dir, exist_ok=True)
        
        file_path = os.path.join(cam_dir, f"{timestamp}.jpg")
        
        # Optimize JPEG quality (85-90) to balance storage size and inference accuracy
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
        success = cv2.imwrite(file_path, frame, encode_param)
        
        if not success:
            logger.error(f"Failed to save frame to {file_path}")
            
        return file_path
