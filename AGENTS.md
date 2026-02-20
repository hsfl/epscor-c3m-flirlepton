# AGENTS.md

## Repository Summary

This repository is a FLIR Lepton thermal imaging toolkit built around USB streaming with `libuvc` and Python `ctypes` bindings.

Current primary workflow:
- Capture thermal frames to `.npy` with metadata sidecar `.json`.
- Analyze captured frame stacks for hotspot detection and temporal behavior.
- Preserve legacy scripts for older `.npz` / `.bin` workflows.

Core stack:
- `libuvc` (system/shared library)
- Python + NumPy + Matplotlib
- Local `uvctypes.py` for UVC constants and binding definitions

## Project Intent

Mission context:
- Support aerial reconnaissance for early wildfire hotspot detection over known lightning-strike locations.

Engineering intent:
- Keep the Lepton pipeline simple, reliable, and maintainable for MVP field use.
- Mirror Boson-style capture/analysis flow where practical.
- Use explicit TODO stubs where hardware calibration or sensor integration is not ready.

Critical constraints:
- Use `libuvc + ctypes` for camera capture.
- Do not switch capture to OpenCV camera APIs.
- Maintain cross-platform behavior for macOS and Linux.

## Primary Scripts

- `lepton-camera.py`
  - Captures Y16 frames from Lepton via `libuvc`.
  - Saves output as `lepton_frames_YYYYMMDD_HHMMSS_###.npy`.
  - Writes session metadata (`.json`) with timing/fps/frame details.
  - Live preview supports wildfire-focused hotspot thresholds and on-the-fly key tuning.

- `view_lepton_npy.py`
  - Loads and validates `.npy` frame stacks.
  - Provides playback and temporal stats plots.
  - Detects hotspots with wildfire profile defaults (`abs`, `delta-over-median`, optional `sigma`).
  - Supports persistence filtering and optional pixel trace.
  - Analysis figure supports live threshold tuning from keyboard.
  - Contains GPS and temperature-conversion stubs/TODOs.

## Fast Navigation (for agents)

Use these first to minimize search time:

- `rg -n "resolve_hotspot_thresholds|HotspotThresholdState|WILDFIRE_" lepton-camera.py view_lepton_npy.py`
  - Finds threshold defaults/profile wiring.
- `rg -n "on_key|key_press_event|Keys:" lepton-camera.py view_lepton_npy.py`
  - Finds live operator controls.
- `rg -n "detect_hotspots|detect_hotspot_in_frame|apply_persistence_filter" view_lepton_npy.py lepton-camera.py`
  - Finds hotspot decision logic.
- `rg -n "raw_to_celsius|TLINEAR_SCALE|KELVIN_TO_CELSIUS_OFFSET" lepton-camera.py view_lepton_npy.py`
  - Finds temperature conversion assumptions.
- `rg -n "frame_time_offsets_sec|capture_start_utc|build_time_axis_from_metadata" lepton-camera.py view_lepton_npy.py`
  - Finds wall-clock timeline path.

## CLI Command Cookbook (for agents)

Use these command blocks first before deeper edits.

Environment/bootstrap:

- `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- `git submodule update --init --recursive`

Quick health checks:

- `python3 uvc-deviceinfo.py`
- `python3 lepton-camera.py --print-device-info --max-frames 30 --output-dir captures`
- `python3 lepton-camera.py --help`
- `python3 view_lepton_npy.py --help`

Mission capture defaults:

- `python3 lepton-camera.py --duration-sec 120 --output-dir captures --live-preview --hotspot-profile wildfire`
- `python3 lepton-camera.py --max-frames 600 --output-dir captures --live-preview --preview-display-mode percentile`
- `python3 lepton-camera.py --max-frames 300 --vid 0x1e4e --pid 0x0100 --output-dir captures`

Mission analysis defaults:

- `python3 view_lepton_npy.py captures/<capture>.npy --playback`
- `python3 view_lepton_npy.py captures/<capture>.npy --profile wildfire --abs-threshold 320 --delta-threshold 35 --min-persistence 3 --threshold-mode all`
- `python3 view_lepton_npy.py captures/<capture>.npy --sigma-threshold 2.5 --min-persistence 3`
- `python3 view_lepton_npy.py captures/<capture>.npy --pixel 80 60`

Capture inventory commands:

- `ls -lt captures/*.npy | head`
- `ls -lt captures/*.json | head`
- `python3 lepton_capture_gui.py captures`

Log/metadata inspection:

- `python3 -m json.tool captures/<capture>.json | head -n 80`
- `rg -n "capture_start_utc|frame_time_offsets_sec|estimated_fps|nominal_fps" captures/<capture>.json`

Preferred search patterns in codebase:

- `rg -n "argparse|add_argument|parse_args|main\\(" lepton-camera.py view_lepton_npy.py`
- `rg -n "Keys:|key_press_event|on_key" lepton-camera.py view_lepton_npy.py`
- `rg -n "resolve_hotspot_thresholds|WILDFIRE_|threshold_mode" lepton-camera.py view_lepton_npy.py`
- `rg -n "raw_to_celsius|TLINEAR_SCALE|KELVIN_TO_CELSIUS_OFFSET" lepton-camera.py view_lepton_npy.py`

Operational note:
- Keep capture pipeline on `libuvc + ctypes`.
- Do not migrate mission capture flow to OpenCV camera APIs.

High-value entry points by function:

- Capture pipeline (`lepton-camera.py`)
  - `main` -> CLI/config and metadata write
  - `capture_frames` -> stream loop + live preview
  - `update_live_preview` -> overlay + per-frame hotspot marker
  - `detect_hotspot_in_frame` -> live threshold evaluation
- Analysis pipeline (`view_lepton_npy.py`)
  - `main` -> load/convert/detect + playback + plots
  - `detect_hotspots` -> per-frame thresholding
  - `apply_persistence_filter` -> temporal run filtering
  - `plot_analysis` -> interactive UI and live threshold retuning
  - `playback_frames` -> playback overlay

## Legacy/Support Scripts

- `readout.py`, `npz_viewer.py`, `temp_viewer.py`, `binary_viewer*.py` remain for older data flows.
- `uvc-deviceinfo.py` and `uvc-radiometry.py` are device diagnostics/utilities.
- `libuvc/` is tracked as a submodule.

## Near-Term TODO Themes

- GPS tagging integration at hotspot events.
- Maps-link action based on hotspot GPS (`https://maps.google.com/?q=LAT,LON`).
- Raw-to-physical temperature calibration once constants are available.
- Timeline axis conversion from frame index to wall-clock capture time.

## Operator Threshold Baseline

Current wildfire-oriented defaults:

- Land mammals usually `36-40C` (background/biological warm objects).
- Fire/smolder screening floor set to `300C` absolute.
- Distinct hotspot requirement: `frame_median + 25C`.
- Combine mode default: `all` (must satisfy enabled thresholds together).

Rationale:
- Reduces false positives from humans/animals and warm terrain.
- Keeps focus on uncontrolled fire-like thermal signatures.
