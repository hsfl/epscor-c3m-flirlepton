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
