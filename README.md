# FLIR Lepton USB Capture (Python + libuvc)

Tiny Python toolkit for streaming raw thermal frames from a **FLIR Lepton** camera over USB with **libuvc**.
Primarily tested on Lepton 3/3.5 modules plugged into a UVC-compatible breakout board.

---

## 📦 Project structure

```
lepton/
├── libuvc/            # C library submodule (pre-built .so / .dll here)
├── readout.py         # Live capture → binary file
├── binary_viewer.py   # Quick-look viewer for captured frames
└── README.md          # You’re reading it
```

---

## 🔧 Prerequisites

| Dependency | Tested version | Notes                                  |
| ---------- | -------------- | -------------------------------------- |
| Python     | ≥ 3.8          | `venv` recommended                     |
| libuvc     | 0.0.7-dev      | Built from source; requires libusb-1.0 |
| NumPy      | ≥ 1.24         | Frame buffer manipulation              |
| Matplotlib | ≥ 3.7          | Optional—plots frames                  |

### *Install libuvc (Linux/macOS)*

```bash
git clone https://github.com/libuvc/libuvc.git
cd libuvc
mkdir build && cd build
cmake ..
make && sudo make install      # installs libuvc and headers
sudo ldconfig                  # Linux only
```

> **Windows** users: grab the pre-built `libuvc.dll` from the official releases or build with MSYS2/MinGW.

---

## 🚀 Quick start

1. **Plug in the Lepton** USB board.
2. Open a terminal in the repo root and run:

```bash
cd libuvc                # step 1 of original notes
python ../readout.py     # start capture
```

### Trouble opening the camera?

If you see `uvc_open_error`:

```bash
sudo chmod -R 777 /dev/bus/usb/    # temporary blanket permission fix
```

Then re-run `python readout.py`.&#x20;

> **Security tip:** For production, create a dedicated `udev` rule instead of `777`.

### Stopping a capture

Press **Ctrl + C** in the terminal.

---

## 🖥️ Viewing your data

```bash
python binary_viewer.py
```

`binary_viewer.py` reads the binary file saved by `readout.py` and plots the frames or dumps them as PNGs. The default path is overwritten on every run—edit the constant at the top of each script if you need unique filenames or directories.&#x20;

---

## ✍️ Changing default paths

Open the script in VS Code:

```bash
code readout.py          # or binary_viewer.py
```

Look for the `OUTPUT_PATH` variable near the top and change it to a new folder so you don’t overwrite previous captures.&#x20;

---

the dennis tagged readout.py and binary_viewer.py is my custom code to allow additional command parameters (for my own testing) specifically for macos
