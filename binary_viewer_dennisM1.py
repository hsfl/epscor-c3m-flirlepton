import os
import numpy as np
import cv2
import argparse

FRAME_WIDTH = 160  # Frame width (dont change these, REFERENCE to camera not output size)
FRAME_HEIGHT = 120  # Frame height

def raw_to_8bit(data):
    # Normalize 16-bit data and convert to 8-bit for display
    cv2.normalize(data, data, 0, 65535, cv2.NORM_MINMAX)
    np.right_shift(data, 8, data)
    return cv2.cvtColor(np.uint8(data), cv2.COLOR_GRAY2RGB)

def load_frame(file_path):
    # Load and reshape the binary data into the frame
    data = np.fromfile(file_path, dtype=np.uint16).reshape(FRAME_HEIGHT, FRAME_WIDTH)
    return data

def main(save_dir):
    # Load all .bin file names from the save directory
    files = sorted([f for f in os.listdir(save_dir) if f.endswith('.bin')])
    if not files:
        print(f"No .bin files found in {save_dir}.")
        return

    total_frames = len(files)
    index = 0
    paused = False
    print(f"Loaded {total_frames} frames from '{save_dir}'.")
    while True:
        file_path = os.path.join(save_dir, files[index])
        try:
            data = load_frame(file_path)
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            # Skip problematic frame
            index = (index + 1) % total_frames
            continue

        img = raw_to_8bit(data)
        cv2.imshow("Binary Viewer for Lepton Radiometry Frames", img)

        # Wait 100 ms for a key press
        key = cv2.waitKey(100) & 0xFF

        if key == ord('q'):
            # Quit the viewer
            break
        elif key == ord('p'):
            # Toggle pause/play mode
            paused = not paused
            print("Paused" if paused else "Playing")
        elif key == ord('a') or key == 81:  # 'a' or left arrow key code
            # Move one frame backward
            index = max(0, index - 1)
        elif key == ord('d') or key == 83:  # 'd' or right arrow key code
            # Move one frame forward
            index = min(total_frames - 1, index + 1)
        else:
            # If not paused and no valid key pressed, automatically advance to the next frame
            if not paused:
                index += 1
                if index >= total_frames:
                    index = 0  # Loop back to the start

    cv2.destroyAllWindows()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Binary Viewer for Lepton Radiometry Frames")
    parser.add_argument("save_dir", help="Directory where the .bin frames are saved")
    args = parser.parse_args()

    main(args.save_dir)
