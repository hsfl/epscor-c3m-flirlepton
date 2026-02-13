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

- `view_lepton_npy.py`
  - Loads and validates `.npy` frame stacks.
  - Provides playback and temporal stats plots.
  - Detects hotspots with sigma and/or absolute thresholding.
  - Supports persistence filtering and optional pixel trace.
  - Contains GPS and temperature-conversion stubs/TODOs.

## Legacy/Support Scripts

- `readout.py`, `npz_viewer.py`, `temp_viewer.py`, `binary_viewer*.py` remain for older data flows.
- `uvc-deviceinfo.py` and `uvc-radiometry.py` are device diagnostics/utilities.
- `libuvc/` is tracked as a submodule.

## Near-Term TODO Themes

- GPS tagging integration at hotspot events.
- Maps-link action based on hotspot GPS (`https://maps.google.com/?q=LAT,LON`).
- Raw-to-physical temperature calibration once constants are available.
- Timeline axis conversion from frame index to wall-clock capture time.
