import os
import numpy as np
import cv2
import threading
import queue
import glob
import statistics

TARGET_DIR = "saved_frames_test_" + input("Enter target directory number: saved_frames_test_")     # Location of npz file from readout.py
DATA_NAME = input("Enter a name for this data set: ")                                              # Name for data exported to txt file
frameData = []                                                                                     # List that stores frame and temp data in string format

# Converts kelvin temperature to celcuis
def ktoc(val):
   return (val - 27315) / 100.0

# Converts kelvin temperature to fahrenheit
def ktof(val):
   return (1.8 * ktoc(val) + 32.0)

# Averages array of temperature values
def getAvgTemp(frame):
    tempAvg = round(statistics.mean(frame), 3)
    return tempAvg

# Exports string items in list frameData to txt file
def exportFrames(frameData): 
    with open(TARGET_DIR + ".txt", "a") as file: 
        file.write("Data set name: " + DATA_NAME + "\n")

        for frames in frameData:
            file.write(frames + "\n")

        file.write("\n")
        file.write("\n")
    
    print("\n" + str(len(frameData)) + " frames successfully exported to " + TARGET_DIR + ".txt")

# Find all .npz files in the directory
npz_files = glob.glob(os.path.join(TARGET_DIR, '*.npz'))

# Print found files
print("Found .npz files:", npz_files)

# Load the first one (or loop over them if needed)
if npz_files:
    npz_file_path = npz_files[0]
    data = np.load(npz_file_path)['frames']
    print("Loaded file:", npz_file_path)
else:
    print("No .npz files found in the directory.")

for i, frame in enumerate(data):
    if frame.dtype != np.uint8:
        frame_8bit = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    else:
        frame_8bit = frame

    # Displays each frame and prints average temperature
    cv2.imshow('Video Playback', frame_8bit)

    avg_temp = getAvgTemp(ktof(frame[i]))
    frameDataConsole = f"Showing frame {i+1}/{len(data)} \033[36mAverage Temperature: {avg_temp:.2f} Fahrenheit\033[0m"
    print(frameDataConsole)

    # Add frame number and average temperature data to frameData list
    frameDataStr = f"Showing frame {i+1}/{len(data)} Average Temperature: {avg_temp:.2f} Fahrenheit"
    frameData.append(frameDataStr)

    key = cv2.waitKey(33)  # Wait ~33 ms
    if key & 0xFF == ord('q'):
        print("Early exit by user")
        break
 
# Exports frameData to txt file
exportFrames(frameData)

cv2.destroyAllWindows()

