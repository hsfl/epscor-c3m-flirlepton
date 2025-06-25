# FLIR Lepton USB Capture Toolkit

Tiny Python toolkit for streaming and saving raw thermal frames from a **FLIR Lepton** camera over USB using **libuvc**. Includes tools for capture, quick viewing, and custom analysis. Primarily tested on Lepton 3/3.5 modules with UVC-compatible breakout boards.

---

## 📁 Project Structure

```
.
├── readout.py                  # Capture frames from Lepton and save as .npz
├── binary_viewer.py            # View saved frames (.bin files)
├── binary_viewer_dennisM1.py   # Custom viewer with CLI for macOS/testing (.bin files)
├── npz_viewer.py               # View saved frames (.npz files) and export temperature data to txt file
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
>
> **macOS:** You must open uvctypes.py and change the file name in line 6 from `libuvc = cdll.LoadLibrary('libuvc.so')` to `libuvc = cdll.LoadLibrary('libuvc.dylib')` so that macOS can find libuvc.

---

## 🚀 Quick Start

1. **Plug in the Lepton** USB board.
2. Open a terminal in the repo root and run:

```bash
python3 readout.py              # Start capture
```
> **Directory:** Enter the directory number when prompted by the terminal. The frames and data from the current capture will be stored in a folder named saved_frames_test_[directory num] in the root repo. The program will overwrite any file named frames.npz within the selected directory, so enter an unused number if you wish to keep any original data. 

3. View saved frames and export temperature data:

```bash
python3 npz_viewer.py                                   # Standard viewer for .npz files

# To export frames as .bin files see customization section before running these commands
# Does not export temperature data
python3 binary_viewer.py                                # Standard viewer for .bin files (uses default save dir)
# OR
python3 binary_viewer_dennisM1.py saved_frames_test_3   # Custom CLI viewer for .bin files (macOS/testing)
```
> **Directory:** Enter the directory number that has the .npz file you wish to view and record temperature data from. The temperature data will be stored in a txt file in the root repo with the same name as the directory selected. 

> **Data Set Name:** Enter a custom name for the current data set. This name will be printed to the txt file. New data sets from the same directory will be stored in the same txt file but appended to the previous data.
---

## 🖥️ Script Details

- **readout.py** — Captures frames from the Lepton and saves as `.npz` file in a custom directory
- **npz_viewer.py** - Loads and displays frames from `.npz` file. Exports average temperature by frame to `.txt` file.
- **binary_viewer.py** — Loads and displays frames from `.bin` files. Uses the default directory (defualt: `saved_frames_test_3`). Edit `SAVE_DIR` if needed.
- **binary_viewer_dennisM1.py** — Custom viewer with command-line argument for directory. Useful for macOS or advanced testing.
- **uvc-deviceinfo.py**, **uvc-radiometry.py** — Utilities for device info and radiometry.

---

## ⚙️ Customization
- By default, `readout.py` will export frames as an `.npz` file. Changes to the program can be made to export frames to `.bin` files:
    1. Un-comment line 144 to call save_frame_to_bin() function
    ```bash
    save_frame_to_bin(data, frame_count)
    ```
    2. Comment out line 186 to prevent frames from being saved as .npz files
    ```bash
    save_frame_to_npz(frame_list)
    ```
- To change which frames are displayed, edit the `SAVE_DIR` variable at the top of `binary_viewer.py`.
- For unique filenames or directories, modify the scripts as needed.

---

## 🛠️ Troubleshooting

- **Camera open error (`uvc_open_error`)**:
  ```bash
  sudo chmod -R 777 /dev/bus/usb/    # Temporary fix (Linux)
  ```
  > For production, create a dedicated `udev` rule instead of using `777` permissions.

  ```bash
  sudo DYLD_FALLBACK_LIBRARY_PATH=/usr/local/lib python3 readout.py # macOS fix- tells macOs dynamic linker where to find uvc libraries if initial search is unsuccessful
  ```

- **macOS notes:**
  - Custom scripts (tagged `dennis`) allow additional command parameters for testing.
  - You may need to grant extra permissions for USB access.

- **Stopping a capture:** Press **Ctrl + C** in the terminal.

---

## 📄 Additional Notes

- All scripts are intended for research and prototyping. Review and adapt for production use as needed.
- For more details, see `lepton_instructions.txt`.
