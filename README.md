# FLIR Lepton USB Capture Toolkit

Python toolkit for capturing and analyzing FLIR Lepton thermal data over USB using `libuvc` + `ctypes`.

## What Is New

This repo now includes an MVP pipeline that matches the Boson-style workflow while staying on a confirmed Lepton path (no OpenCV camera capture):

- `lepton-camera.py`: capture Y16 thermal frames and save to `.npy` (optional live preview with per-frame min/max Celsius overlay)
- `view_lepton_npy.py`: playback + hotspot analysis from `.npy` (playback now shows per-frame min/max Celsius overlay)
- `lepton_capture_gui.py`: fast folder-based preview and rename tool for `.npy` captures

Legacy scripts are still present for prior workflows.

## Project Structure

```text
.
├── lepton-camera.py            # New libuvc capture app (.npy + metadata .json)
├── view_lepton_npy.py          # New viewer/analyzer for .npy stacks
├── lepton_capture_gui.py       # Quick GUI preview + rename tool for capture folders
├── readout.py                  # Legacy capture script (.npz flow)
├── npz_viewer.py               # Legacy .npz viewer
├── temp_viewer.py              # Legacy per-pixel average temperature heatmap
├── binary_viewer.py            # Legacy .bin frame viewer
├── binary_viewer_dennisM1.py   # Legacy CLI .bin frame viewer
├── uvc-deviceinfo.py           # Device info utility
├── uvc-radiometry.py           # Radiometry utility
├── uvctypes.py                 # ctypes bindings/constants for libuvc
└── libuvc/                     # libuvc source submodule
```

## Prerequisites

- Python 3.8+
- `libuvc` installed and discoverable by the system loader
- Python packages: `numpy`, `matplotlib`

## Setup

```bash
cd /Users/sozodennis/Developer/epscor-c3m-flirlepton
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install `libuvc` if needed:

```bash
git submodule update --init --recursive
cd libuvc
mkdir -p build && cd build
cmake ..
make
sudo make install
sudo ldconfig   # Linux only
```

On macOS, `sudo` may be required to open the camera over `libusb`.

## Quick Start

### 1) Capture a session to `.npy`

Capture by frame count:

```bash
python3 lepton-camera.py --max-frames 600 --output-dir captures
```

Capture by duration:

```bash
python3 lepton-camera.py --duration-sec 120 --output-dir captures
```

Capture with live preview window:

```bash
python3 lepton-camera.py --duration-sec 120 --output-dir captures --live-preview
```

Use a different preview colormap:

```bash
python3 lepton-camera.py --duration-sec 120 --output-dir captures --live-preview --preview-colormap magma
```

Manual VID/PID override:

```bash
python3 lepton-camera.py --max-frames 300 --vid 0x1e4e --pid 0x0100
```

Output naming format:

- `lepton_frames_YYYYMMDD_HHMMSS_001.npy`
- sidecar metadata: same basename with `.json`

### 2) View and analyze `.npy`

```bash
python3 view_lepton_npy.py captures/lepton_frames_YYYYMMDD_HHMMSS_001.npy
```

During playback, the overlay includes:

- frame index
- per-frame min temperature in Celsius
- per-frame max temperature in Celsius
- hotspot coordinates when detected

Plot-only mode (skip playback):

```bash
python3 view_lepton_npy.py captures/lepton_frames_YYYYMMDD_HHMMSS_001.npy --no-playback
```

With hotspot detection:

```bash
python3 view_lepton_npy.py captures/lepton_frames_YYYYMMDD_HHMMSS_001.npy --sigma-threshold 2.5 --min-persistence 3
```

Absolute threshold example:

```bash
python3 view_lepton_npy.py captures/lepton_frames_YYYYMMDD_HHMMSS_001.npy --abs-threshold 60
```

Combined thresholding:

```bash
python3 view_lepton_npy.py captures/lepton_frames_YYYYMMDD_HHMMSS_001.npy --sigma-threshold 2.0 --abs-threshold 60 --threshold-mode all
```

Optional pixel trace:

```bash
python3 view_lepton_npy.py captures/lepton_frames_YYYYMMDD_HHMMSS_001.npy --pixel 80 60
```

Interactive review controls (analysis figure):

- hover over the temporal graph to scrub frames in the preview panel
- left-click on the graph to lock the selected frame
- double-left-click on the graph to unlock and return to hover-follow mode
- temporal x-axis uses local wall-clock time when metadata includes capture start + frame offsets
- if timestamp metadata is unavailable/invalid, x-axis falls back to frame index
- preview overlays always show the frame max pixel marker
- preview overlays also show the threshold hotspot marker when detection is present

### 3) Quickly preview and rename capture files (GUI)

```bash
python3 lepton_capture_gui.py captures
```

Useful controls:

- select a file in the left list to load it
- scrub the frame slider to inspect any frame quickly
- use Play/Pause to auto-advance frames (adjust FPS in the control row)
- press Left/Right arrow for previous/next file
- edit the rename box and press Enter (or click Rename)
- when a sidecar JSON exists, it is renamed with the `.npy` automatically

## CLI Help

```bash
python3 lepton-camera.py --help
python3 view_lepton_npy.py --help
```

## Notes and TODO Stubs

- GPS integration is stubbed in `view_lepton_npy.py` and marked with TODO comments.
- Temperature conversion assumes Lepton 3.5 defaults (Radiometry ON, TLinear ON, 0.01 K), using `C = (raw / 100) - 273.15`.
- Timeline axis uses local wall-clock time when metadata is available, otherwise frame index fallback.

## Troubleshooting

- `uvc_open` access denied:
  - macOS: run with `sudo`
  - Linux: prefer a proper `udev` rule over broad permission changes
- `libuvc` load failure:
  - confirm `sudo make install` and library loader path setup
- No hotspots detected:
  - lower `--sigma-threshold`, use `--abs-threshold`, or lower `--min-persistence`
