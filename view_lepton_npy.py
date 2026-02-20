#!/usr/bin/env python3
"""View and analyze FLIR Lepton .npy frame stacks."""

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

TLINEAR_SCALE = 100.0  # Lepton 3.5 default: raw centi-Kelvin (0.01 K)
KELVIN_TO_CELSIUS_OFFSET = 273.15
WILDFIRE_ABS_THRESHOLD_C = 300.0
WILDFIRE_DELTA_THRESHOLD_C = 25.0
WILDFIRE_SIGMA_THRESHOLD = None
WILDFIRE_THRESHOLD_MODE = "all"


@dataclass
class HotspotThresholdState:
    absolute_threshold: Optional[float]
    delta_threshold: Optional[float]
    sigma_threshold: Optional[float]
    threshold_mode: str


def resolve_hotspot_thresholds(
    profile: str,
    absolute_threshold: Optional[float],
    delta_threshold: Optional[float],
    sigma_threshold: Optional[float],
    threshold_mode: str,
) -> HotspotThresholdState:
    if profile == "wildfire":
        resolved_abs = WILDFIRE_ABS_THRESHOLD_C if absolute_threshold is None else absolute_threshold
        resolved_delta = WILDFIRE_DELTA_THRESHOLD_C if delta_threshold is None else delta_threshold
        resolved_sigma = WILDFIRE_SIGMA_THRESHOLD if sigma_threshold is None else sigma_threshold
        resolved_mode = threshold_mode if threshold_mode else WILDFIRE_THRESHOLD_MODE
        return HotspotThresholdState(
            absolute_threshold=resolved_abs,
            delta_threshold=resolved_delta,
            sigma_threshold=resolved_sigma,
            threshold_mode=resolved_mode,
        )
    return HotspotThresholdState(
        absolute_threshold=absolute_threshold,
        delta_threshold=delta_threshold,
        sigma_threshold=sigma_threshold,
        threshold_mode=threshold_mode,
    )


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


def compute_frame_max_coords(frames: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_frames, _height, width = frames.shape
    flat_frames = frames.reshape(n_frames, -1)
    flat_indices = np.argmax(flat_frames, axis=1)
    ys, xs = np.divmod(flat_indices, width)
    values = frames[np.arange(n_frames), ys, xs]
    return xs.astype(np.int32), ys.astype(np.int32), values.astype(np.float64)


def build_time_axis_from_metadata(
    metadata: Optional[dict], n_frames: int
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    if not metadata:
        return None, None

    capture_start_utc = metadata.get("capture_start_utc")
    offsets = metadata.get("frame_time_offsets_sec")
    if not isinstance(capture_start_utc, str) or not isinstance(offsets, list):
        return None, None
    if len(offsets) != n_frames:
        return None, None

    try:
        start_utc = datetime.fromisoformat(capture_start_utc.replace("Z", "+00:00"))
    except ValueError:
        return None, None

    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=timezone.utc)
    else:
        start_utc = start_utc.astimezone(timezone.utc)

    try:
        x_seconds = np.asarray(offsets, dtype=np.float64)
    except (TypeError, ValueError):
        return None, None

    if x_seconds.shape != (n_frames,) or not np.isfinite(x_seconds).all():
        return None, None

    start_local = start_utc.astimezone()
    x_datetimes_local = np.array([start_local + timedelta(seconds=float(s)) for s in x_seconds], dtype=object)
    return x_seconds, x_datetimes_local


def raw_to_celsius(frame: np.ndarray) -> np.ndarray:
    # Assumes Lepton 3.5 defaults: Radiometry ON, TLinear ON, 0.01 K resolution.
    # Celsius = (raw / 100.0) - 273.15
    frame_f32 = frame.astype(np.float32, copy=False)
    return (frame_f32 / TLINEAR_SCALE) - KELVIN_TO_CELSIUS_OFFSET


def detect_hotspots(
    frames: np.ndarray,
    sigma_threshold: Optional[float],
    absolute_threshold: Optional[float],
    delta_threshold: Optional[float],
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
        frame_median = float(np.median(frame))

        masks: List[np.ndarray] = []
        if sigma_threshold is not None:
            sigma_cutoff = frame_mean + sigma_threshold * frame_std
            masks.append(frame >= sigma_cutoff)
        if absolute_threshold is not None:
            masks.append(frame >= absolute_threshold)
        if delta_threshold is not None:
            masks.append(frame >= (frame_median + delta_threshold))

        if not masks:
            continue

        mask = masks[0]
        for candidate in masks[1:]:
            if threshold_mode == "all":
                mask = np.logical_and(mask, candidate)
            else:
                mask = np.logical_or(mask, candidate)

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
    initial_thresholds: HotspotThresholdState,
    min_persistence: int,
    pixel: Optional[Tuple[int, int]],
    colormap: str,
    x_seconds: Optional[np.ndarray],
    x_datetimes_local: Optional[np.ndarray],
) -> None:
    n_frames = frames.shape[0]
    max_xs, max_ys, max_values = compute_frame_max_coords(frames)
    use_timestamps = (
        x_seconds is not None
        and x_datetimes_local is not None
        and x_seconds.shape == (n_frames,)
        and x_datetimes_local.shape == (n_frames,)
    )

    if pixel is None:
        fig, axes = plt.subplots(2, 1, figsize=(11, 8), constrained_layout=True)
        ax_stats, ax_preview = axes
    else:
        fig, axes = plt.subplots(3, 1, figsize=(11, 10), constrained_layout=True)
        ax_stats, ax_pixel, ax_preview = axes

    frame_idx = np.arange(frames.shape[0])
    x_plot = frame_idx.astype(np.float64)
    if use_timestamps:
        x_plot = mdates.date2num(x_datetimes_local.tolist())

    ax_stats.plot(x_plot, means, label="Mean", color="tab:blue")
    ax_stats.plot(x_plot, mins, label="Min", color="tab:green")
    ax_stats.plot(x_plot, maxs, label="Max", color="tab:orange")

    hotspot_scatter = ax_stats.scatter([], [], color="red", s=20, label="Hotspot frame")

    ax_stats.set_title("Temporal Statistics (Celsius)")
    ax_stats.set_xlabel("Local capture time (HH:MM:SS)" if use_timestamps else "Frame index")
    ax_stats.set_ylabel("Temperature (°C)")
    ax_stats.grid(True, alpha=0.3)
    if use_timestamps:
        ax_stats.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        fig.autofmt_xdate(rotation=0, ha="center")

    if pixel is not None:
        x, y = pixel
        trace = frames[:, y, x]
        ax_pixel.plot(x_plot, trace, color="tab:purple")
        ax_pixel.set_title(f"Pixel Trace (x={x}, y={y})")
        ax_pixel.set_xlabel("Local capture time (HH:MM:SS)" if use_timestamps else "Frame index")
        ax_pixel.set_ylabel("Temperature (°C)")
        ax_pixel.grid(True, alpha=0.3)
        if use_timestamps:
            ax_pixel.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))

    preview_idx = int(np.argmax(maxs))
    preview_image = ax_preview.imshow(frames[preview_idx], cmap=colormap)
    preview_image.set_clim(float(np.min(frames)), float(np.max(frames)))
    max_marker, = ax_preview.plot(
        [],
        [],
        marker="o",
        linestyle="None",
        markerfacecolor="none",
        markeredgecolor="cyan",
        markeredgewidth=2,
        markersize=8,
        label="Frame max pixel",
    )
    detection_marker, = ax_preview.plot(
        [],
        [],
        marker="x",
        linestyle="None",
        color="red",
        markeredgewidth=2,
        markersize=9,
        label="Threshold hotspot",
    )
    ax_preview.set_title(f"Preview Frame (index {preview_idx})")
    ax_preview.set_axis_off()
    ax_preview.legend(loc="upper right")
    preview_text = ax_preview.text(
        0.02,
        0.98,
        "",
        transform=ax_preview.transAxes,
        va="top",
        color="white",
        fontsize=10,
        bbox=dict(facecolor="black", alpha=0.55, edgecolor="none", boxstyle="round,pad=0.25"),
    )

    cursor_line = ax_stats.axvline(x_plot[preview_idx], color="black", linestyle="--", linewidth=1.2, alpha=0.5)
    active_marker, = ax_stats.plot([], [], "ko", markerfacecolor="white", markersize=7, markeredgewidth=1.5)
    status_text = ax_stats.text(
        0.02,
        0.98,
        "",
        transform=ax_stats.transAxes,
        va="top",
        color="black",
        fontsize=9,
        bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", boxstyle="round,pad=0.2"),
    )
    ax_stats.legend(loc="best")

    state = {
        "active_idx": preview_idx,
        "locked": False,
        "last_hover_xy": None,
        "thresholds": HotspotThresholdState(
            absolute_threshold=initial_thresholds.absolute_threshold,
            delta_threshold=initial_thresholds.delta_threshold,
            sigma_threshold=initial_thresholds.sigma_threshold,
            threshold_mode=initial_thresholds.threshold_mode,
        ),
        "min_persistence": max(1, int(min_persistence)),
        "detections": np.zeros(n_frames, dtype=bool),
        "coords": [None] * n_frames,
        "peak_values": np.full(n_frames, np.nan, dtype=np.float64),
    }

    def recompute_detections() -> None:
        thresholds = state["thresholds"]
        detections_raw, coords_raw, peak_values_raw = detect_hotspots(
            frames,
            sigma_threshold=thresholds.sigma_threshold,
            absolute_threshold=thresholds.absolute_threshold,
            delta_threshold=thresholds.delta_threshold,
            threshold_mode=thresholds.threshold_mode,
        )
        detections = apply_persistence_filter(detections_raw, state["min_persistence"])
        coords: List[Optional[Tuple[int, int]]] = [None] * len(coords_raw)
        peak_values = np.full_like(peak_values_raw, np.nan)
        for i, detected in enumerate(detections):
            if detected and coords_raw[i] is not None:
                coords[i] = coords_raw[i]
                peak_values[i] = peak_values_raw[i]
        state["detections"] = detections
        state["coords"] = coords
        state["peak_values"] = peak_values

        hotspot_indices = np.flatnonzero(detections)
        if hotspot_indices.size > 0:
            offsets = np.column_stack((x_plot[hotspot_indices], peak_values[hotspot_indices]))
            hotspot_scatter.set_offsets(offsets)
        else:
            hotspot_scatter.set_offsets(np.empty((0, 2)))

    def format_threshold_value(value: Optional[float], unit: str) -> str:
        if value is None:
            return "off"
        return f"{value:.1f}{unit}"

    def update_active_frame(idx: int, source_xy: Optional[Tuple[float, float]] = None) -> None:
        idx = int(np.clip(idx, 0, n_frames - 1))
        state["active_idx"] = idx
        if source_xy is not None:
            state["last_hover_xy"] = source_xy

        preview_image.set_data(frames[idx])
        if use_timestamps:
            local_ts = x_datetimes_local[idx]
            ts_text = local_ts.strftime("%Y-%m-%d %H:%M:%S")
            ax_preview.set_title(f"Preview Frame (index {idx}) | Local {ts_text}")
        else:
            ax_preview.set_title(f"Preview Frame (index {idx})")

        max_x = int(max_xs[idx])
        max_y = int(max_ys[idx])
        max_temp = float(max_values[idx])
        max_marker.set_data([max_x], [max_y])
        preview_text.set_text(f"Frame {idx} | Max {max_temp:.2f}°C")

        detection = state["coords"][idx]
        if detection is not None:
            det_x, det_y = detection
            detection_marker.set_data([det_x], [det_y])
            det_temp = float(frames[idx, det_y, det_x])
            detection_text = f"Threshold hotspot=({det_x}, {det_y}) {det_temp:.2f}°C"
        else:
            detection_marker.set_data([], [])
            detection_text = "Threshold hotspot=none"

        cursor_line.set_xdata([x_plot[idx], x_plot[idx]])
        active_marker.set_data([x_plot[idx]], [maxs[idx]])

        hover_xy = state["last_hover_xy"]
        if hover_xy is None:
            hover_text = "Graph (x,y)=n/a"
        else:
            hover_x, hover_y = hover_xy
            if np.isfinite(hover_x) and np.isfinite(hover_y):
                hover_text = f"Graph (x,y)=({hover_x:.2f}, {hover_y:.2f})"
            else:
                hover_text = "Graph (x,y)=n/a"

        lock_text = "ON" if state["locked"] else "OFF"
        if use_timestamps:
            time_text = f"Local time={x_datetimes_local[idx].strftime('%Y-%m-%d %H:%M:%S')}"
        else:
            time_text = "Local time=n/a"
        thresholds = state["thresholds"]
        threshold_text = (
            f"abs={format_threshold_value(thresholds.absolute_threshold, 'C')} "
            f"delta={format_threshold_value(thresholds.delta_threshold, 'C')} "
            f"sigma={format_threshold_value(thresholds.sigma_threshold, '')} "
            f"mode={thresholds.threshold_mode} "
            f"persist={state['min_persistence']}"
        )
        status_text.set_text(
            f"Frame {idx} | lock={lock_text} | {hover_text}\n"
            f"{time_text}\n"
            f"{threshold_text}\n"
            f"Min/Mean/Max={mins[idx]:.2f}/{means[idx]:.2f}/{maxs[idx]:.2f} °C\n"
            f"Frame max=({max_x}, {max_y}) {max_temp:.2f}°C | {detection_text}\n"
            "Keys: [/]=abs  ,/.=delta  -/+=sigma  m=mode  n/N=persist"
        )
        fig.canvas.draw_idle()

    def x_to_index(x_value: Optional[float]) -> Optional[int]:
        if x_value is None or not np.isfinite(x_value):
            return None
        if use_timestamps:
            return int(np.argmin(np.abs(x_plot - float(x_value))))
        return int(np.clip(np.rint(x_value), 0, n_frames - 1))

    def on_motion(event) -> None:
        if event.inaxes is not ax_stats or state["locked"]:
            return
        idx = x_to_index(event.xdata)
        if idx is None:
            return
        y_value = float(event.ydata) if event.ydata is not None else float("nan")
        update_active_frame(idx, source_xy=(float(event.xdata), y_value))

    def on_click(event) -> None:
        if event.inaxes is not ax_stats or event.button != 1:
            return
        idx = x_to_index(event.xdata)
        if idx is None:
            return
        y_value = float(event.ydata) if event.ydata is not None else float("nan")
        if event.dblclick:
            state["locked"] = False
        else:
            state["locked"] = True
        update_active_frame(idx, source_xy=(float(event.xdata), y_value))

    def on_key(event) -> None:
        key = event.key
        if key is None:
            return
        thresholds = state["thresholds"]
        changed = False

        if key == "[":
            if thresholds.absolute_threshold is not None:
                thresholds.absolute_threshold = max(0.0, thresholds.absolute_threshold - 10.0)
                changed = True
        elif key == "]":
            base = thresholds.absolute_threshold if thresholds.absolute_threshold is not None else WILDFIRE_ABS_THRESHOLD_C
            thresholds.absolute_threshold = base + 10.0
            changed = True
        elif key == ",":
            if thresholds.delta_threshold is not None:
                thresholds.delta_threshold = max(0.0, thresholds.delta_threshold - 2.0)
                changed = True
        elif key == ".":
            base = thresholds.delta_threshold if thresholds.delta_threshold is not None else WILDFIRE_DELTA_THRESHOLD_C
            thresholds.delta_threshold = base + 2.0
            changed = True
        elif key == "-":
            if thresholds.sigma_threshold is not None:
                thresholds.sigma_threshold = max(0.0, thresholds.sigma_threshold - 0.25)
                changed = True
        elif key in ("+", "="):
            base = thresholds.sigma_threshold if thresholds.sigma_threshold is not None else 2.5
            thresholds.sigma_threshold = base + 0.25
            changed = True
        elif key.lower() == "m":
            thresholds.threshold_mode = "any" if thresholds.threshold_mode == "all" else "all"
            changed = True
        elif key == "n":
            state["min_persistence"] = max(1, state["min_persistence"] - 1)
            changed = True
        elif key == "N":
            state["min_persistence"] += 1
            changed = True

        if changed:
            recompute_detections()
            update_active_frame(state["active_idx"])

    fig.canvas.mpl_connect("motion_notify_event", on_motion)
    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)
    recompute_detections()
    update_active_frame(preview_idx)

    plt.show()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="View/analyze Lepton .npy thermal captures")
    parser.add_argument("input", help="Path to .npy file generated by lepton-camera.py")
    parser.add_argument("--fps", type=float, default=None, help="Playback FPS override (default: metadata estimated_fps, then 8.0)")
    parser.add_argument("--colormap", default="inferno", help="Matplotlib colormap for thermal display")
    parser.add_argument("--profile", choices=["none", "wildfire"], default="wildfire", help="Hotspot threshold preset")
    parser.add_argument("--sigma-threshold", type=float, default=None, help="Detect hotspots above mean + sigma*std per frame (Celsius)")
    parser.add_argument("--abs-threshold", type=float, default=None, help="Detect hotspots above absolute Celsius threshold")
    parser.add_argument("--delta-threshold", type=float, default=None, help="Detect hotspots above frame median + delta (Celsius)")
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
    x_seconds, x_datetimes_local = build_time_axis_from_metadata(metadata, temp_frames.shape[0])

    if args.pixel is not None:
        x, y = args.pixel
        width = raw_frames.shape[2]
        height = raw_frames.shape[1]
        if x < 0 or x >= width or y < 0 or y >= height:
            print(f"Pixel out of bounds. Valid x:[0,{width - 1}], y:[0,{height - 1}]")
            return 2

    means, mins, maxs = compute_temporal_stats(temp_frames)
    thresholds = resolve_hotspot_thresholds(
        profile=args.profile,
        absolute_threshold=args.abs_threshold,
        delta_threshold=args.delta_threshold,
        sigma_threshold=args.sigma_threshold,
        threshold_mode=args.threshold_mode,
    )

    if thresholds.sigma_threshold is None and thresholds.absolute_threshold is None and thresholds.delta_threshold is None:
        print("No hotspot threshold configured. Set --sigma-threshold and/or --abs-threshold to enable detections.")

    detections_raw, coords_raw, peak_values_raw = detect_hotspots(
        temp_frames,
        sigma_threshold=thresholds.sigma_threshold,
        absolute_threshold=thresholds.absolute_threshold,
        delta_threshold=thresholds.delta_threshold,
        threshold_mode=thresholds.threshold_mode,
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
    print(
        "Thresholds: "
        f"profile={args.profile} "
        f"abs={thresholds.absolute_threshold}C "
        f"delta={thresholds.delta_threshold}C "
        f"sigma={thresholds.sigma_threshold} "
        f"mode={thresholds.threshold_mode} "
        f"min_persistence={max(1, args.min_persistence)}"
    )

    if not args.no_playback:
        playback_frames(temp_frames, detections, coords, playback_fps, args.colormap)

    plot_analysis(
        temp_frames,
        means,
        mins,
        maxs,
        thresholds,
        max(1, args.min_persistence),
        tuple(args.pixel) if args.pixel is not None else None,
        args.colormap,
        x_seconds,
        x_datetimes_local,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
