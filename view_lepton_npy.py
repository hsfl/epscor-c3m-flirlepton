#!/usr/bin/env python3
"""View and analyze FLIR Lepton .npy frame stacks."""

import argparse
import json
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np

TLINEAR_SCALE = 100.0  # Lepton 3.5 default: raw centi-Kelvin (0.01 K)
KELVIN_TO_CELSIUS_OFFSET = 273.15


def load_frames(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    data = np.load(path)
    if not isinstance(data, np.ndarray):
        raise ValueError("Loaded object is not a NumPy ndarray")
    if data.ndim != 3:
        raise ValueError(f"Expected frame stack with shape (N, H, W), got shape {data.shape}")
    if data.shape[0] == 0:
        raise ValueError("Input frame stack has zero frames")
    if data.dtype not in (np.uint16, np.float32, np.float64, np.int16, np.uint8, np.int32, np.uint32):
        raise ValueError(f"Unsupported dtype for thermal stack: {data.dtype}")

    return data


def load_metadata(npy_path: Path) -> Optional[dict]:
    sidecar = npy_path.with_suffix(".json")
    if not sidecar.exists():
        return None

    try:
        with sidecar.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def compute_temporal_stats(frames: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    means = frames.mean(axis=(1, 2))
    mins = frames.min(axis=(1, 2))
    maxs = frames.max(axis=(1, 2))
    return means, mins, maxs


def raw_to_celsius(frame: np.ndarray) -> np.ndarray:
    # Assumes Lepton 3.5 defaults: Radiometry ON, TLinear ON, 0.01 K resolution.
    # Celsius = (raw / 100.0) - 273.15
    frame_f32 = frame.astype(np.float32, copy=False)
    return (frame_f32 / TLINEAR_SCALE) - KELVIN_TO_CELSIUS_OFFSET


def detect_hotspots(
    frames: np.ndarray,
    sigma_threshold: Optional[float],
    absolute_threshold: Optional[float],
    threshold_mode: str,
) -> Tuple[np.ndarray, List[Optional[Tuple[int, int]]], np.ndarray]:
    n_frames = frames.shape[0]
    detections = np.zeros(n_frames, dtype=bool)
    coords: List[Optional[Tuple[int, int]]] = [None] * n_frames
    peak_values = np.zeros(n_frames, dtype=np.float64)

    for i in range(n_frames):
        frame = frames[i]
        frame_mean = float(frame.mean())
        frame_std = float(frame.std())

        sigma_mask = None
        if sigma_threshold is not None:
            sigma_cutoff = frame_mean + sigma_threshold * frame_std
            sigma_mask = frame >= sigma_cutoff

        abs_mask = None
        if absolute_threshold is not None:
            abs_mask = frame >= absolute_threshold

        if sigma_mask is None and abs_mask is None:
            continue

        if sigma_mask is not None and abs_mask is not None:
            mask = np.logical_or(sigma_mask, abs_mask) if threshold_mode == "any" else np.logical_and(sigma_mask, abs_mask)
        else:
            mask = sigma_mask if sigma_mask is not None else abs_mask

        if mask is None or not mask.any():
            continue

        masked_frame = np.where(mask, frame, -np.inf)
        flat_idx = int(np.argmax(masked_frame))
        y, x = np.unravel_index(flat_idx, frame.shape)
        detections[i] = True
        coords[i] = (int(x), int(y))
        peak_values[i] = float(frame[y, x])

    return detections, coords, peak_values


def apply_persistence_filter(detections: np.ndarray, min_persistence: int) -> np.ndarray:
    if min_persistence <= 1:
        return detections.copy()

    filtered = np.zeros_like(detections)
    start = None

    for i, value in enumerate(detections):
        if value and start is None:
            start = i
        if not value and start is not None:
            run_len = i - start
            if run_len >= min_persistence:
                filtered[start:i] = True
            start = None

    if start is not None:
        run_len = len(detections) - start
        if run_len >= min_persistence:
            filtered[start:] = True

    return filtered


def gps_tag_hotspot_stub(frame_index: int, hotspot_xy: Tuple[int, int]) -> None:
    # TODO: Replace this stub with real GPS data acquisition and association logic.
    # TODO: Add click-to-open Google Maps URL when LAT/LON are available:
    # https://maps.google.com/?q=LAT,LON
    _ = (frame_index, hotspot_xy)


def playback_frames(
    frames: np.ndarray,
    detections: np.ndarray,
    coords: Sequence[Optional[Tuple[int, int]]],
    fps: float,
    colormap: str,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_title("Lepton Playback (Celsius)")
    image = ax.imshow(frames[0], cmap=colormap)
    marker, = ax.plot([], [], "ro", markersize=8, markerfacecolor="none", markeredgewidth=2)
    text = ax.text(
        0.02,
        0.98,
        "",
        transform=ax.transAxes,
        va="top",
        color="white",
        fontsize=10,
        bbox=dict(facecolor="black", alpha=0.45, edgecolor="none", boxstyle="round,pad=0.25"),
    )
    plt.colorbar(image, ax=ax, label="Temperature (°C)")

    frame_delay = 1.0 / max(fps, 1e-6)
    frame_mins = frames.min(axis=(1, 2))
    frame_maxs = frames.max(axis=(1, 2))

    for i in range(frames.shape[0]):
        image.set_data(frames[i])
        min_c = float(frame_mins[i])
        max_c = float(frame_maxs[i])
        if detections[i] and coords[i] is not None:
            x, y = coords[i]
            marker.set_data([x], [y])
            text.set_text(
                f"Frame {i} | Min {min_c:.2f}°C | Max {max_c:.2f}°C\n"
                f"Hotspot @ ({x}, {y})"
            )
        else:
            marker.set_data([], [])
            text.set_text(f"Frame {i} | Min {min_c:.2f}°C | Max {max_c:.2f}°C")

        fig.canvas.draw_idle()
        if not plt.fignum_exists(fig.number):
            break
        plt.pause(frame_delay)

    plt.close(fig)


def plot_analysis(
    frames: np.ndarray,
    means: np.ndarray,
    mins: np.ndarray,
    maxs: np.ndarray,
    detections: np.ndarray,
    peak_values: np.ndarray,
    pixel: Optional[Tuple[int, int]],
    colormap: str,
) -> None:
    hotspot_indices = np.flatnonzero(detections)

    if pixel is None:
        fig, axes = plt.subplots(2, 1, figsize=(11, 8), constrained_layout=True)
        ax_stats, ax_preview = axes
    else:
        fig, axes = plt.subplots(3, 1, figsize=(11, 10), constrained_layout=True)
        ax_stats, ax_pixel, ax_preview = axes

    frame_idx = np.arange(frames.shape[0])

    # TODO: Convert x-axis from frame index to human-readable capture time using start time + frame timestamps/fps.
    ax_stats.plot(frame_idx, means, label="Mean", color="tab:blue")
    ax_stats.plot(frame_idx, mins, label="Min", color="tab:green")
    ax_stats.plot(frame_idx, maxs, label="Max", color="tab:orange")

    if hotspot_indices.size > 0:
        ax_stats.scatter(hotspot_indices, peak_values[hotspot_indices], color="red", s=20, label="Hotspot frame")

    ax_stats.set_title("Temporal Statistics (Celsius)")
    ax_stats.set_xlabel("Frame index")
    ax_stats.set_ylabel("Temperature (°C)")
    ax_stats.grid(True, alpha=0.3)
    ax_stats.legend(loc="best")

    if pixel is not None:
        x, y = pixel
        trace = frames[:, y, x]
        ax_pixel.plot(frame_idx, trace, color="tab:purple")
        ax_pixel.set_title(f"Pixel Trace (x={x}, y={y})")
        ax_pixel.set_xlabel("Frame index")
        ax_pixel.set_ylabel("Temperature (°C)")
        ax_pixel.grid(True, alpha=0.3)

    preview_idx = int(np.argmax(maxs))
    ax_preview.imshow(frames[preview_idx], cmap=colormap)
    ax_preview.set_title(f"Preview Frame (index {preview_idx})")
    ax_preview.set_axis_off()

    plt.show()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="View/analyze Lepton .npy thermal captures")
    parser.add_argument("input", help="Path to .npy file generated by lepton-camera.py")
    parser.add_argument("--fps", type=float, default=None, help="Playback FPS override (default: metadata estimated_fps, then 8.0)")
    parser.add_argument("--colormap", default="inferno", help="Matplotlib colormap for thermal display")
    parser.add_argument("--sigma-threshold", type=float, default=None, help="Detect hotspots above mean + sigma*std per frame (Celsius)")
    parser.add_argument("--abs-threshold", type=float, default=None, help="Detect hotspots above absolute Celsius threshold")
    parser.add_argument(
        "--threshold-mode",
        choices=["any", "all"],
        default="any",
        help="How to combine sigma and absolute thresholds when both are provided",
    )
    parser.add_argument("--min-persistence", type=int, default=1, help="Minimum consecutive hotspot frames required")
    parser.add_argument("--pixel", nargs=2, type=int, metavar=("X", "Y"), help="Optional per-pixel temporal trace")
    parser.add_argument("--no-playback", action="store_true", help="Skip frame playback and only show plots")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()

    try:
        raw_frames = load_frames(input_path)
    except Exception as exc:
        print(f"Load error: {exc}")
        return 1

    metadata = load_metadata(input_path)
    if args.fps is not None:
        playback_fps = args.fps
    elif metadata and isinstance(metadata.get("estimated_fps"), (int, float)) and metadata["estimated_fps"] > 0:
        playback_fps = float(metadata["estimated_fps"])
    elif metadata and isinstance(metadata.get("nominal_fps"), (int, float)) and metadata["nominal_fps"] > 0:
        playback_fps = float(metadata["nominal_fps"])
    else:
        playback_fps = 8.0

    print(f"Loaded: {input_path}")
    print(f"Shape: {raw_frames.shape}, dtype: {raw_frames.dtype}")
    print(f"Playback fps: {playback_fps:.3f}")
    print("Conversion: assuming Lepton 3.5 TLinear ON at 0.01 K resolution.")

    temp_frames = raw_to_celsius(raw_frames)

    if args.pixel is not None:
        x, y = args.pixel
        width = raw_frames.shape[2]
        height = raw_frames.shape[1]
        if x < 0 or x >= width or y < 0 or y >= height:
            print(f"Pixel out of bounds. Valid x:[0,{width - 1}], y:[0,{height - 1}]")
            return 2

    means, mins, maxs = compute_temporal_stats(temp_frames)

    if args.sigma_threshold is None and args.abs_threshold is None:
        print("No hotspot threshold configured. Set --sigma-threshold and/or --abs-threshold to enable detections.")

    detections_raw, coords_raw, peak_values_raw = detect_hotspots(
        temp_frames,
        sigma_threshold=args.sigma_threshold,
        absolute_threshold=args.abs_threshold,
        threshold_mode=args.threshold_mode,
    )
    detections = apply_persistence_filter(detections_raw, max(1, args.min_persistence))

    coords: List[Optional[Tuple[int, int]]] = [None] * len(coords_raw)
    peak_values = np.full_like(peak_values_raw, np.nan)
    for i, detected in enumerate(detections):
        if detected and coords_raw[i] is not None:
            coords[i] = coords_raw[i]
            peak_values[i] = peak_values_raw[i]

    event_count = 0
    previous = False
    for i, detected in enumerate(detections):
        if detected and not previous and coords[i] is not None:
            gps_tag_hotspot_stub(i, coords[i])
            event_count += 1
        previous = detected

    print(f"Hotspot frames: {int(detections.sum())} / {len(detections)}")
    print(f"Hotspot events (after persistence filter): {event_count}")

    if not args.no_playback:
        playback_frames(temp_frames, detections, coords, playback_fps, args.colormap)

    plot_analysis(
        temp_frames,
        means,
        mins,
        maxs,
        detections,
        np.nan_to_num(peak_values, nan=means),
        tuple(args.pixel) if args.pixel is not None else None,
        args.colormap,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
