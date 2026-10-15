import os
import numpy as np
import cv2
from datetime import datetime
import matplotlib.pyplot as plt

# Converts kelvin temperature to celcuis
def ktoc(val):
   return (val - 27315) / 100.0

# Converts kelvin temperature to fahrenheit
def ktof(val):
   return (1.8 * ktoc(val) + 32.0)

# Averages array of temperature values
def getAvgTemp(data):
    tempAvg = np.mean(data, axis=0)
    return tempAvg

if __name__ == "__main__":

    TARGET_DIR = "saved_frames_test_" + input("Enter target directory number: saved_frames_test_")     # Location of npz file from readout.py
    NPZ_FILE_NAME = input("Enter a file name (no spaces): ") + ".npz"

    # Full path of file
    npz_file_path = os.path.join(TARGET_DIR, NPZ_FILE_NAME)

    # Check if the file exists
    if os.path.exists(npz_file_path):
        data = np.load(npz_file_path)['frames']
        print("Loaded file:", npz_file_path)
        print("Frame shape:", data.shape)
    else:
        print("File not found:", npz_file_path)

    # Creates average temp in fahrenheit
    avg_temp_arr = getAvgTemp(ktof(data))

    for i, frame in enumerate(data):
        if frame.dtype != np.uint8:
            frame_8bit = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        else:
            frame_8bit = frame

        key = cv2.waitKey(33)  # Wait ~33 ms
        if key & 0xFF == ord('q'):
            print("Early exit by user")
            break
    
    # Display average temperature per pixel rounded nearest thousands place
    for temp in avg_temp_arr:
        print(np.round(temp, 3))

    print("Height: " + str(len(avg_temp_arr)))
    print("Width: " + str(len(avg_temp_arr[0])))

    plt.figure(figsize=(10, 7))
    plt.imshow(avg_temp_arr, cmap='inferno')  # or 'hot', 'coolwarm'
    plt.colorbar(label='Avg Temp (°F)')
    plt.title('Average Temperature Heatmap')
    plt.axis('off')  # Optional: hides pixel axis ticks
    plt.tight_layout()
    plt.show()


    cv2.destroyAllWindows()