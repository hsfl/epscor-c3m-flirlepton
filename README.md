# FLIR Lepton USB Capture Toolkit

Tiny Python toolkit for streaming and saving raw thermal frames from a **FLIR Lepton** camera over USB using **libuvc**. Includes tools for capture, quick viewing, and custom analysis. Primarily tested on Lepton 3/3.5 modules with UVC-compatible breakout boards.

---

## 📁 Project Structure

```
.
├── readout.py                  # Capture frames from Lepton and save as .bin
├── binary_viewer.py            # View saved frames (standard)
├── binary_viewer_dennisM1.py   # Custom viewer with CLI for macOS/testing
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
python3 readout.py              # Start capture (frames saved to ./saved_frames_test_3/ by default)
```

3. To view saved frames:

```bash
python3 binary_viewer.py        # Standard viewer (uses default save dir)
# OR
python3 binary_viewer_dennisM1.py saved_frames_test_3   # Custom CLI viewer (macOS/testing)
```
---

## 🖥️ Script Details

- **readout.py** — Captures frames from the Lepton and saves as `.bin` files in a directory (default: `saved_frames_test_3`). Edit `SAVE_DIR` at the top to change output location.
- **binary_viewer.py** — Loads and displays frames from the default directory. Edit `SAVE_DIR` if needed.
- **binary_viewer_dennisM1.py** — Custom viewer with command-line argument for directory. Useful for macOS or advanced testing.
- **uvc-deviceinfo.py**, **uvc-radiometry.py** — Utilities for device info and radiometry.

---

## ⚙️ Customization

- To change where frames are saved, edit the `SAVE_DIR` variable at the top of `readout.py` and `binary_viewer.py`.
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
