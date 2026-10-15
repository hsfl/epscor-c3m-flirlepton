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

### macOS setup

From the repository root, use a virtual environment and install the native library
with [Homebrew](https://formulae.brew.sh/formula/libuvc):

```bash
brew install libuvc
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -c "import uvctypes; print('Loaded:', uvctypes.libuvc._name)"
python readout.py
```

No edits to `uvctypes.py` are needed. The loader tries system discovery and the
standard Apple Silicon (`/opt/homebrew/lib`) and Intel (`/usr/local/lib`) locations.
Python and libuvc must use the same architecture. If multiple installations exist,
you can select one explicitly:

```bash
LIBUVC_LIBRARY="$(brew --prefix libuvc)/lib/libuvc.dylib" .venv/bin/python readout.py
```

### Install libuvc from source (Linux or custom macOS installation)

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
> **macOS:** Use the setup above; do not change the library filename in the source.

---

## 🚀 Quick Start

1. **Plug in the Lepton** USB board.
2. Open a terminal in the repo root and run:

```bash
# Linux
python3 readout.py

# macOS (with .venv activated)
python readout.py
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
> **Data Set Name:** Enter a custom name for the current data set. This name will be printed to the txt file. New data sets from the same directory will be stored in the same txt file but appended to the previous data.
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

  **Linux**
  ```bash
  # Temporary USB permission fix for testing only
  sudo chmod -R 777 /dev/bus/usb/

  # Test camera detection and capture
  python3 uvc-deviceinfo.py
  python3 readout.py
  ```
  **Note:** On Linux, changing USB device permissions with `chmod 777` is an insecure temporary workaround. For regular use, configure a `udev` rule to grant access to the camera without requiring root privileges.

  **macOS**
  ```bash
  # Test library loading and camera detection first
  .venv/bin/python -c "import uvctypes; print(uvctypes.libuvc._name)"
  .venv/bin/python uvc-deviceinfo.py
  ```

  Library loading failures are separate from USB permission failures. If loading
  reports `incompatible architecture`, use a libuvc build matching your Python
  (`.venv/bin/python -c "import platform; print(platform.machine())"`).
  `LIBUVC_LIBRARY=/absolute/path/to/libuvc.dylib` selects a particular build.

  **Do not run `sudo python readout.py`, `sudo python3 readout.py`, or an
  equivalent command using the virtual environment interpreter on macOS.**
  During testing on macOS Tahoe 26.4, normal execution returned
  `uvc_open error (-3): Access denied`, while elevated capture was reported to
  make the entire Mac restart or become unresponsive. Console logs confirmed a
  kernel panic during that session. The exact triggering USB operation has not
  been established.

  Do not use `sudo` to bypass this access error or repeatedly retry a capture
  that causes a system crash. Camera privacy permission alone may not resolve
  exclusive USB access restrictions. Check macOS and camera-board firmware
  compatibility with the vendor before attempting capture again. Python buffer
  handling fixes do not resolve an operating-system kernel panic.

  A related [upstream libusb report](https://github.com/libusb/libusb/issues/1762)
  documents a whole-system panic when claiming a USB interface on Tahoe 26.3.1
  with different hardware. It is a relevant lead, not confirmation of this
  project's exact failure or a verified fix.

- **macOS notes:**
  - Custom scripts (tagged `dennis`) allow additional command parameters for testing.
  - Camera privacy prompts may not appear for this libusb/libuvc path because it does not use AVFoundation.

- **Stopping a capture:** Press **Ctrl + C** in the terminal.

---

## 📄 Additional Notes

- All scripts are intended for research and prototyping. Review and adapt for production use as needed.
- For more details, see `lepton_instructions.txt`.
