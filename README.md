# FLIR Lepton USB Capture Toolkit

Mission-focused FLIR Lepton capture and analysis using `libuvc` + `ctypes` (no OpenCV camera API path).

## Mission Operations Workflow

This software is intended for early wildfire hotspot screening during aerial reconnaissance over known lightning-strike zones.

Standard mission loop:
1. Preflight checks and device validation.
2. Timed capture session to `.npy` + `.json` metadata.
3. Immediate hotspot review and threshold tuning.
4. Archive/rename capture sets for downstream triage.

Primary scripts:
- `lepton-camera.py`: live capture and mission-time threshold monitoring.
- `view_lepton_npy.py`: post-capture playback and hotspot event analysis.
- `lepton_capture_gui.py`: quick browse/rename for captured sessions.

## Setup

One-time setup (first install):

```bash
# 1) Go to your project folder (change this path to where you put the repo)
cd ~/epscor-c3m-flirlepton

# 2) Create and activate a Python environment
python3 -m venv .venv
source .venv/bin/activate

# 3) Install required Python packages
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

Daily start (every time you open a new terminal):

```bash
cd ~/epscor-c3m-flirlepton
source .venv/bin/activate
```

If you are not sure where the repo is located, run:

```bash
pwd
ls
```

## Preflight Checklist

Run these before flight ops:

```bash
python3 uvc-deviceinfo.py
python3 lepton-camera.py --print-device-info --max-frames 30 --output-dir captures --live-preview
```

Validate:
- Device opens successfully.
- Y16 stream is detected.
- Preview renders stable temperature range.
- Output files are written in `captures/`.

## Capture During Mission

Recommended baseline (2-minute sweep with live preview):

```bash
python3 lepton-camera.py \
  --duration-sec 120 \
  --output-dir captures \
  --live-preview \
  --hotspot-profile wildfire \
  --preview-display-mode percentile \
  --preview-colormap inferno
```

Wildfire profile defaults:
- `abs = 300C`
- `delta = frame_median + 25C`
- `mode = all`

Manual VID/PID override (if auto-discovery fails):

```bash
python3 lepton-camera.py --max-frames 300 --vid 0x1e4e --pid 0x0100 --output-dir captures
```

Live mission key controls (capture window):
- `[` / `]`: adjust absolute threshold (`10C`)
- `,` / `.`: adjust delta threshold (`2C`)
- `-` / `+`: adjust sigma threshold (`0.25`)
- `m`: toggle threshold mode (`any`/`all`)
- `f` / `F`: adjust display floor
- `c` / `C`: adjust display ceiling
- `v`: cycle display mode
- `r`: reset display bounds

Outputs:
- `lepton_frames_YYYYMMDD_HHMMSS_###.npy`
- Matching metadata sidecar `.json` with timing fields (`capture_start_utc`, `frame_time_offsets_sec`).

## Post-Capture Analysis

Run full hotspot analysis:

```bash
python3 view_lepton_npy.py captures/lepton_frames_YYYYMMDD_HHMMSS_001.npy --playback
```

Analyze the newest capture automatically (no filename typing):

```bash
python3 view_lepton_npy.py "$(ls -t captures/lepton_frames_*.npy | head -n 1)" --playback
```

Mission-oriented stricter screening:

```bash
python3 view_lepton_npy.py \
  captures/lepton_frames_YYYYMMDD_HHMMSS_001.npy \
  --profile wildfire \
  --abs-threshold 320 \
  --delta-threshold 35 \
  --min-persistence 3 \
  --threshold-mode all
```

Additional examples:

```bash
python3 view_lepton_npy.py captures/lepton_frames_YYYYMMDD_HHMMSS_001.npy --sigma-threshold 2.5 --min-persistence 3
python3 view_lepton_npy.py captures/lepton_frames_YYYYMMDD_HHMMSS_001.npy --pixel 80 60
python3 view_lepton_npy.py captures/lepton_frames_YYYYMMDD_HHMMSS_001.npy --fps 8 --playback
```

Analysis key controls (plot window):
- `[` / `]`, `,` / `.`, `-` / `+`, `m`: threshold tuning
- `n` / `N`: persistence tuning
- `f` / `F`, `c` / `C`, `v`, `r`: display tuning

## Capture Management (GUI)

```bash
python3 lepton_capture_gui.py captures
```

Use for rapid frame scrubbing, session-by-session comparison, and coordinated rename of `.npy` plus sidecar `.json`.

## CLI Reference

```bash
python3 lepton-camera.py --help
python3 view_lepton_npy.py --help
```

High-use `lepton-camera.py` options:
- `--duration-sec`, `--max-frames`, `--output-dir`, `--live-preview`
- `--hotspot-profile`, `--hotspot-abs-threshold`, `--hotspot-delta-threshold`, `--hotspot-sigma-threshold`, `--hotspot-threshold-mode`
- `--preview-display-mode`, `--preview-display-pct-low`, `--preview-display-pct-high`, `--preview-fixed-min-c`, `--preview-fixed-max-c`

High-use `view_lepton_npy.py` options:
- `--playback`, `--fps`, `--profile`
- `--abs-threshold`, `--delta-threshold`, `--sigma-threshold`, `--threshold-mode`, `--min-persistence`
- `--display-mode`, `--display-pct-low`, `--display-pct-high`, `--display-fixed-min-c`, `--display-fixed-max-c`

## Troubleshooting

- `uvc_open failed` / access denied:
  - macOS: retry with `sudo`.
  - Linux: prefer proper `udev` rules.
- `libuvc` load failure:
  - confirm install path and dynamic loader configuration.
- Too many false positives:
  - raise `--abs-threshold` and/or `--delta-threshold`, increase `--min-persistence`.
- Missed likely hotspots:
  - lower `--abs-threshold` or `--delta-threshold`, optionally enable `--sigma-threshold`.

## Notes

- Temperature conversion currently assumes Lepton 3.5 defaults (`C = raw/100 - 273.15`).
- GPS/event geotagging paths are intentionally stubbed for future integration.
