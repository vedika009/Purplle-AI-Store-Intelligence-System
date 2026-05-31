import cv2
cap = cv2.VideoCapture('./data/raw/CCTV Footage-20260529T160731Z-3-00144614ea/CCTV Footage/CAM 1.mp4')
print("Width:", cap.get(cv2.CAP_PROP_FRAME_WIDTH))
print("Height:", cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
cap.release()
