# FLIR Lepton USB Capture Toolkit

Tiny Python toolkit for streaming and saving raw thermal frames from a **FLIR Lepton** camera over USB using **libuvc**. Includes tools for capture, quick viewing, and custom analysis. Primarily tested on Lepton 3/3.5 modules with UVC-compatible breakout boards.

---

## 📁 Project Structure

```
.
├── readout.py                  # Capture frames from Lepton and save as .npz
├── binary_viewer.py            # View saved frames (.bin files)
├── binary_viewer_dennisM1.py   # Custom viewer with CLI for macOS/testing (.bin files)
├── npz_viewer.py               # View saved frames (.npz files) 
├── temp_viewer.py              # Averages temperature values across a single data set
├── compare_temp.py             # Gives the difference in average temperatures between 2 data sets 
├── uvc-deviceinfo.py           # Device info utility
├── uvc-radiometry.py           # Radiometry utility
├── uvctypes.py                 # UVC ctypes definitions
├── saved_frames_test_2/        # Example output directory for frames
├── standard-units.yaml         # Reference data
└── lepton_instructions.txt     # Additional notes

```

---

## 🔧 Prerequisites

- **Python** ≥ 3.8  
  Recommended: use a virtual environment (`python -m venv venv`)
- **NumPy** ≥ 1.24
- **OpenCV** (Python package, for image processing)
- **Matplotlib** (optional, for plotting)
- **libuvc** (system library, built from source)

### Install Python dependencies

```bash
pip install numpy opencv-python matplotlib
```

### Install libuvc (Linux/macOS)

```bash
git clone https://github.com/libuvc/libuvc.git
cd libuvc
mkdir build && cd build
cmake ..
make && sudo make install      # installs libuvc and headers
sudo ldconfig                  # Linux only
```

> **Windows:** Use the pre-built `libuvc.dll` from official releases or build with MSYS2/MinGW.

---

## 🚀 Quick Start

1. **Plug in the Lepton** USB board.
2. Open a terminal in the repo root and run:

```bash
# Linux
python3 readout.py

# macOS
sudo python3 readout.py         # macOS may require root for libusb/uvc_open
```
> **Directory and File Name:** Enter the directory number when prompted by the terminal. The frames and data from the current capture will be stored in a folder named saved_frames_test_[directory num] in the root repo. Enter a custom name for the npz file (do not include  spaces or .npz)

3. View saved frames:

```bash
python3 npz_viewer.py                                   # Standard viewer for .npz files

# To export frames as .bin files see customization section before running these commands
python3 binary_viewer.py                                # Standard viewer for .bin files (uses default save dir)
# OR
python3 binary_viewer_dennisM1.py saved_frames_test_3   # Custom CLI viewer for .bin files (macOS/testing)
```
> **Directory:** Enter the directory number that has the .npz file you wish to view along with the file name. 

4. Analyze temperature data:

```bash
python3 temp_viewer.py          # Average Temperature Values 

python3 compare_temp.py         # Average Temperature Difference 
```                             
> **Directory and File Name:** Enter the target directory number and name of the npz file that you wish to get temperature data from when prompted by the terminal. For `compare_temp.py` you will be prompted to enter in a directory and file name twice, once for each data set.

> **Temperature Output:** For temp_viewer.py, you will see a heat map of the average temperature of 1 data set. For compare_temp.py, you will see a heat map of the absolute difference in temperature between your 2 data sets. Additionaly, in the terminal you will recieve the temperature difference array (120, 160) with red values having a statistically significant difference.

---

## 🖥️ Script Details

- **readout.py** — Captures frames from the Lepton and saves as `.npz` file in a custom directory
- **npz_viewer.py** - Loads and displays frames from `.npz` file. 
- **binary_viewer.py** — Loads and displays frames from `.bin` files. Uses the default directory (defualt: `saved_frames_test_3`). Edit `SAVE_DIR` if needed.
- **binary_viewer_dennisM1.py** — Custom viewer with command-line argument for directory. Useful for macOS or advanced testing.
- **temp_viewer.py** - Calculates average temerature across all frames and displays heat map.
- **compare_temp.py** - Compares average temperature between 2 datasets and displays heat map of difference.
- **uvc-deviceinfo.py**, **uvc-radiometry.py** — Utilities for device info and radiometry.

---

## ⚙️ Customization
- By default, `readout.py` will export frames as an `.npz` file. Changes to the program can be made to export frames to `.bin` files:
    1. Un-comment line 144 to call save_frame_to_bin() function
    ```bash
    save_frame_to_bin(data, frame_count)
    ```
    2. Comment out line 213 to prevent frames from being saved as .npz files
    ```bash
    save_frame_to_npz(frame_list)
    ```
- To change which frames are displayed, edit the `SAVE_DIR` variable at the top of `binary_viewer.py`.
- For unique filenames or directories, modify the scripts as needed.

---

## 🛠️ Troubleshooting

- **Camera open error (`uvc_open_error`)**:
  ```bash
  # Linux quick test fix
  sudo chmod -R 777 /dev/bus/usb/
  python3 uvc-deviceinfo.py
  python3 readout.py

  # macOS
  sudo python3 uvc-deviceinfo.py
  sudo python3 readout.py
  ```
  > On recent macOS releases, libusb may need root (or USB capture entitlements) to detach the UVC kernel driver.
  >
  > On Linux, prefer a dedicated `udev` rule for persistent access instead of `chmod 777`.

- **macOS notes:**
  - Custom scripts (tagged `dennis`) allow additional command parameters for testing.
  - Camera privacy prompts may not appear for this libusb/libuvc path because it does not use AVFoundation.

- **Stopping a capture:** Press **Ctrl + C** in the terminal.

---

## 📄 Additional Notes

- All scripts are intended for research and prototyping. Review and adapt for production use as needed.
- For more details, see `lepton_instructions.txt`.
