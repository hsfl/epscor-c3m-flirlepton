import os
import numpy as np
import cv2

TARGET_DIR = "saved_frames_test_" + input("Enter target directory number: saved_frames_test_")     # Location of npz file from readout.py
NPZ_FILE_NAME = input("Enter file name: ") + ".npz"

# Full path of file
npz_file_path = os.path.join(TARGET_DIR, NPZ_FILE_NAME)

# Check if the file exists
if os.path.exists(npz_file_path):
    data = np.load(npz_file_path)['frames']
    print("Loaded file:", npz_file_path)
    print("Frame shape:", data.shape)
else:
    print("File not found:", npz_file_path)


for i, frame in enumerate(data):
    if frame.dtype != np.uint8:
        frame_8bit = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    else:
        frame_8bit = frame

    # Displays each frame and prints average temperature
    cv2.imshow('Video Playback', frame_8bit)

    key = cv2.waitKey(33)  # Wait ~33 ms
    if key & 0xFF == ord('q'):
        print("Early exit by user")
        break
 
cv2.destroyAllWindows()

