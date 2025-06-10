import os
import numpy as np
import cv2
import threading
import queue

SAVE_DIR = "saved_frames_test_3"  # Directory where frames are saved
FRAME_WIDTH = 160  # Frame width
FRAME_HEIGHT = 120  # Frame height

def raw_to_8bit(data):
    cv2.normalize(data, data, 0, 65535, cv2.NORM_MINMAX)
    np.right_shift(data, 8, data)
    return cv2.cvtColor(np.uint8(data), cv2.COLOR_GRAY2RGB)

def display_frames(queue):
    cv2.namedWindow('Frame', cv2.WINDOW_NORMAL)

    while True:
        data = queue.get()

        if data is None:
            break

        img = raw_to_8bit(data)
        cv2.imshow('Frame', img)

        key = cv2.waitKey(50)

        if key == ord('q'):  # Quit if 'q' is pressed
            break

    cv2.destroyAllWindows()

def read_frames(queue):
    # Get a list of all .bin files in the directory
    files = [f for f in os.listdir(SAVE_DIR) if f.endswith('.bin')]
    files.sort()  # Sort files to read them in order

    for file in files:
        file_path = os.path.join(SAVE_DIR, file)
        
        # Read the binary data
        data = np.fromfile(file_path, dtype=np.uint16).reshape(FRAME_HEIGHT, FRAME_WIDTH)
        queue.put(data)

    queue.put(None)  # Signal the end of frames

if __name__ == '__main__':
    frame_queue = queue.Queue()

    # Start the display thread
    display_thread = threading.Thread(target=display_frames, args=(frame_queue,))
    display_thread.start()

    # Read frames in the main thread
    read_frames(frame_queue)

    # Wait for the display thread to finish
    display_thread.join()