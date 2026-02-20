#!/usr/bin/env python3
"""Capture FLIR Lepton thermal frames via libuvc and save as .npy stack."""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from ctypes import CFUNCTYPE, POINTER, byref, c_uint16, c_void_p, cast
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Dict, List, Optional, Tuple

import numpy as np

TLINEAR_SCALE = 100.0  # Lepton 3.5 default: raw centi-Kelvin (0.01 K)
KELVIN_TO_CELSIUS_OFFSET = 273.15
WILDFIRE_ABS_THRESHOLD_C = 300.0
WILDFIRE_DELTA_THRESHOLD_C = 25.0
WILDFIRE_SIGMA_THRESHOLD = None
WILDFIRE_THRESHOLD_MODE = "all"
DISPLAY_MODE_CHOICES = ("percentile", "minmax", "fixed", "global")
DISPLAY_WINDOW_EPSILON_C = 0.01


@dataclass
class HotspotThresholdState:
    absolute_threshold: Optional[float]
    delta_threshold: Optional[float]
    sigma_threshold: Optional[float]
    threshold_mode: str


@dataclass
class DisplayWindowState:
    mode: str
    pct_low: float
    pct_high: float
    fixed_min_c: Optional[float]
    fixed_max_c: Optional[float]
    manual_floor_c: Optional[float] = None
    manual_ceiling_c: Optional[float] = None
    global_min_c: Optional[float] = None
    global_max_c: Optional[float] = None


def clamp_percentiles(low: float, high: float) -> Tuple[float, float]:
    low = float(np.clip(low, 0.0, 100.0))
    high = float(np.clip(high, 0.0, 100.0))
    if high <= low:
        low, high = 1.0, 99.0
    return low, high


def ensure_valid_window(vmin: float, vmax: float) -> Tuple[float, float]:
    if not np.isfinite(vmin) or not np.isfinite(vmax):
        return 0.0, 1.0
    if vmax <= vmin:
        center = 0.5 * (vmin + vmax)
        return center - DISPLAY_WINDOW_EPSILON_C, center + DISPLAY_WINDOW_EPSILON_C
    return float(vmin), float(vmax)


def compute_display_window(frame: np.ndarray, state: DisplayWindowState) -> Tuple[float, float]:
    frame_min = float(np.min(frame))
    frame_max = float(np.max(frame))
    pct_low, pct_high = clamp_percentiles(state.pct_low, state.pct_high)
    pct_vmin, pct_vmax = np.percentile(frame, [pct_low, pct_high]).astype(np.float64)

    if state.mode == "minmax":
        base_vmin, base_vmax = frame_min, frame_max
    elif state.mode == "fixed":
        if (
            state.fixed_min_c is not None
            and state.fixed_max_c is not None
            and np.isfinite(state.fixed_min_c)
            and np.isfinite(state.fixed_max_c)
            and state.fixed_max_c > state.fixed_min_c
        ):
            base_vmin, base_vmax = float(state.fixed_min_c), float(state.fixed_max_c)
        else:
            base_vmin, base_vmax = float(pct_vmin), float(pct_vmax)
    elif state.mode == "global":
        if (
            state.global_min_c is not None
            and state.global_max_c is not None
            and np.isfinite(state.global_min_c)
            and np.isfinite(state.global_max_c)
            and state.global_max_c > state.global_min_c
        ):
            base_vmin, base_vmax = float(state.global_min_c), float(state.global_max_c)
        else:
            base_vmin, base_vmax = float(pct_vmin), float(pct_vmax)
    else:
        base_vmin, base_vmax = float(pct_vmin), float(pct_vmax)

    vmin = float(state.manual_floor_c) if state.manual_floor_c is not None else base_vmin
    vmax = float(state.manual_ceiling_c) if state.manual_ceiling_c is not None else base_vmax
    return ensure_valid_window(vmin, vmax)


def cycle_display_mode(mode: str) -> str:
    if mode not in DISPLAY_MODE_CHOICES:
        return DISPLAY_MODE_CHOICES[0]
    idx = DISPLAY_MODE_CHOICES.index(mode)
    return DISPLAY_MODE_CHOICES[(idx + 1) % len(DISPLAY_MODE_CHOICES)]


def nudge_display_floor(state: DisplayWindowState, frame: np.ndarray, delta_c: float) -> None:
    cur_vmin, cur_vmax = compute_display_window(frame, state)
    base_floor = state.manual_floor_c if state.manual_floor_c is not None else cur_vmin
    new_floor = float(base_floor + delta_c)
    if new_floor >= cur_vmax:
        new_floor = cur_vmax - DISPLAY_WINDOW_EPSILON_C
    state.manual_floor_c = new_floor


def nudge_display_ceiling(state: DisplayWindowState, frame: np.ndarray, delta_c: float) -> None:
    cur_vmin, cur_vmax = compute_display_window(frame, state)
    base_ceiling = state.manual_ceiling_c if state.manual_ceiling_c is not None else cur_vmax
    new_ceiling = float(base_ceiling + delta_c)
    if new_ceiling <= cur_vmin:
        new_ceiling = cur_vmin + DISPLAY_WINDOW_EPSILON_C
    state.manual_ceiling_c = new_ceiling


def format_display_state(state: DisplayWindowState, vmin: float, vmax: float) -> str:
    mode_text = state.mode
    if state.mode == "percentile":
        mode_text = f"{state.mode}({state.pct_low:.1f}-{state.pct_high:.1f}%)"
    elif state.mode == "fixed":
        if state.fixed_min_c is not None and state.fixed_max_c is not None:
            mode_text = f"{state.mode}({state.fixed_min_c:.1f},{state.fixed_max_c:.1f}C)"
        else:
            mode_text = f"{state.mode}(fallback=percentile)"
    return f"display={mode_text} win={vmin:.2f}-{vmax:.2f}C"


def build_display_state(
    mode: str,
    pct_low: float,
    pct_high: float,
    fixed_min_c: Optional[float],
    fixed_max_c: Optional[float],
) -> DisplayWindowState:
    resolved_mode = mode if mode in DISPLAY_MODE_CHOICES else "percentile"
    resolved_pct_low, resolved_pct_high = clamp_percentiles(pct_low, pct_high)
    return DisplayWindowState(
        mode=resolved_mode,
        pct_low=resolved_pct_low,
        pct_high=resolved_pct_high,
        fixed_min_c=fixed_min_c,
        fixed_max_c=fixed_max_c,
    )


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


def parse_hex_or_int(value: str) -> int:
    value = value.strip().lower()
    if value.startswith("0x"):
        return int(value, 16)
    return int(value)


def load_uvc_module():
    try:
        import uvctypes  # noqa: PLC0415

        return uvctypes
    except SystemExit as exc:
        raise RuntimeError("Failed to load libuvc via uvctypes. Verify libuvc is installed and discoverable.") from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise RuntimeError(f"Failed to import uvctypes: {exc}") from exc


def ensure_stop_condition(max_frames: Optional[int], duration_sec: Optional[float]) -> None:
    if max_frames is None and duration_sec is None:
        raise ValueError("You must provide at least one stop condition: --max-frames or --duration-sec")
    if max_frames is not None and max_frames <= 0:
        raise ValueError("--max-frames must be > 0")
    if duration_sec is not None and duration_sec <= 0:
        raise ValueError("--duration-sec must be > 0")


def create_filename(output_dir: Path, prefix: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pattern = re.compile(rf"^{re.escape(prefix)}_{timestamp}_(\d{{3}})\.npy$")
    existing = []
    for candidate in output_dir.glob(f"{prefix}_{timestamp}_*.npy"):
        match = pattern.match(candidate.name)
        if match:
            existing.append(int(match.group(1)))

    next_index = 1 if not existing else max(existing) + 1
    return output_dir / f"{prefix}_{timestamp}_{next_index:03d}.npy"


def discover_device(uvc, ctx, vid: Optional[int], pid: Optional[int]):
    dev = POINTER(uvc.uvc_device)()

    candidates: List[Tuple[int, int, str]] = []
    if vid is not None and pid is not None:
        candidates.append((vid, pid, "manual override"))
    else:
        candidates.append((uvc.PT_USB_VID, uvc.PT_USB_PID, "default PT_USB_VID/PT_USB_PID"))
        candidates.append((0, 0, "any UVC device fallback"))

    tried: List[str] = []
    for candidate_vid, candidate_pid, label in candidates:
        res = uvc.libuvc.uvc_find_device(ctx, byref(dev), candidate_vid, candidate_pid, 0)
        tried.append(f"{label} (VID=0x{candidate_vid:04x}, PID=0x{candidate_pid:04x}) -> {res}")
        if res >= 0:
            return dev, candidate_vid, candidate_pid

    tried_text = "\n  ".join(tried)
    raise RuntimeError(f"No matching camera found. Tried:\n  {tried_text}")


def save_session_metadata(metadata_path: Path, metadata: Dict) -> None:
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def raw_to_celsius(frame: np.ndarray) -> np.ndarray:
    frame_f32 = frame.astype(np.float32, copy=False)
    return (frame_f32 / TLINEAR_SCALE) - KELVIN_TO_CELSIUS_OFFSET


def detect_hotspot_in_frame(
    frame_celsius: np.ndarray,
    thresholds: HotspotThresholdState,
) -> Optional[Tuple[int, int, float]]:
    frame_mean = float(frame_celsius.mean())
    frame_std = float(frame_celsius.std())
    frame_median = float(np.median(frame_celsius))

    masks: List[np.ndarray] = []
    if thresholds.sigma_threshold is not None:
        sigma_cutoff = frame_mean + thresholds.sigma_threshold * frame_std
        masks.append(frame_celsius >= sigma_cutoff)
    if thresholds.absolute_threshold is not None:
        masks.append(frame_celsius >= thresholds.absolute_threshold)
    if thresholds.delta_threshold is not None:
        masks.append(frame_celsius >= (frame_median + thresholds.delta_threshold))

    if not masks:
        return None

    mask = masks[0]
    for candidate in masks[1:]:
        if thresholds.threshold_mode == "all":
            mask = np.logical_and(mask, candidate)
        else:
            mask = np.logical_or(mask, candidate)

    if not mask.any():
        return None

    masked_frame = np.where(mask, frame_celsius, -np.inf)
    flat_idx = int(np.argmax(masked_frame))
    y, x = np.unravel_index(flat_idx, frame_celsius.shape)
    return int(x), int(y), float(frame_celsius[y, x])


def init_live_preview(colormap: str):
    import matplotlib.pyplot as plt  # noqa: PLC0415

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_title("Lepton Live Preview (Celsius)")
    placeholder = np.zeros((60, 80), dtype=np.float32)
    image = ax.imshow(placeholder, cmap=colormap)
    marker, = ax.plot(
        [],
        [],
        marker="x",
        linestyle="None",
        color="red",
        markeredgewidth=2,
        markersize=9,
        label="Threshold hotspot",
    )
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
    ax.legend(loc="upper right")
    plt.colorbar(image, ax=ax, label="Temperature (°C)")
    plt.show(block=False)
    return plt, fig, image, marker, text


def format_threshold_value(value: Optional[float], unit: str) -> str:
    if value is None:
        return "off"
    return f"{value:.1f}{unit}"


def update_live_preview(
    plt,
    fig,
    image,
    marker,
    text,
    frame_idx: int,
    frame_celsius: np.ndarray,
    thresholds: HotspotThresholdState,
    display_state: DisplayWindowState,
) -> bool:
    if not plt.fignum_exists(fig.number):
        return False

    frame_min = float(frame_celsius.min())
    frame_max = float(frame_celsius.max())
    image.set_data(frame_celsius)
    vmin, vmax = compute_display_window(frame_celsius, display_state)
    image.set_clim(vmin, vmax)

    hotspot = detect_hotspot_in_frame(frame_celsius, thresholds)
    if hotspot is not None:
        hx, hy, htemp = hotspot
        marker.set_data([hx], [hy])
        hotspot_text = f"Hotspot=({hx}, {hy}) {htemp:.2f}°C"
    else:
        marker.set_data([], [])
        hotspot_text = "Hotspot=none"

    threshold_text = (
        f"abs={format_threshold_value(thresholds.absolute_threshold, 'C')} "
        f"delta={format_threshold_value(thresholds.delta_threshold, 'C')} "
        f"sigma={format_threshold_value(thresholds.sigma_threshold, '')} "
        f"mode={thresholds.threshold_mode}"
    )
    text.set_text(
        f"Frame {frame_idx} | Min {frame_min:.2f}°C | Max {frame_max:.2f}°C\n"
        f"{hotspot_text}\n"
        f"{format_display_state(display_state, vmin, vmax)}\n"
        f"{threshold_text}\n"
        "Keys: [/]=abs  ,/.=delta  -/+=sigma  m=mode  f/F=floor  c/C=ceil  v=disp  r=reset"
    )
    fig.canvas.draw_idle()
    plt.pause(0.001)
    return True


def capture_frames(
    uvc,
    devh,
    ctrl,
    max_frames: Optional[int],
    duration_sec: Optional[float],
    nominal_fps: float,
    live_preview: bool,
    preview_colormap: str,
    hotspot_thresholds: HotspotThresholdState,
    preview_display: DisplayWindowState,
) -> Tuple[List[np.ndarray], List[float], float]:
    frame_queue: Queue = Queue(maxsize=8)
    capture_start_monotonic = time.monotonic()
    frame_times: List[float] = []
    plt = fig = image = marker = text = None
    threshold_state = HotspotThresholdState(
        absolute_threshold=hotspot_thresholds.absolute_threshold,
        delta_threshold=hotspot_thresholds.delta_threshold,
        sigma_threshold=hotspot_thresholds.sigma_threshold,
        threshold_mode=hotspot_thresholds.threshold_mode,
    )
    display_state = DisplayWindowState(
        mode=preview_display.mode,
        pct_low=preview_display.pct_low,
        pct_high=preview_display.pct_high,
        fixed_min_c=preview_display.fixed_min_c,
        fixed_max_c=preview_display.fixed_max_c,
        manual_floor_c=preview_display.manual_floor_c,
        manual_ceiling_c=preview_display.manual_ceiling_c,
        global_min_c=preview_display.global_min_c,
        global_max_c=preview_display.global_max_c,
    )
    preview_runtime = {"last_idx": -1, "last_frame_c": None}

    def py_frame_callback(frame, _userptr):
        if frame.contents.data_bytes != 2 * frame.contents.width * frame.contents.height:
            return

        array_ptr = cast(
            frame.contents.data,
            POINTER(c_uint16 * (frame.contents.width * frame.contents.height)),
        )
        data = np.frombuffer(array_ptr.contents, dtype=np.uint16).reshape(
            frame.contents.height,
            frame.contents.width,
        ).copy()

        ts = time.monotonic()
        if not frame_queue.full():
            frame_queue.put((data, ts))

    callback = CFUNCTYPE(None, POINTER(uvc.uvc_frame), c_void_p)(py_frame_callback)

    res = uvc.libuvc.uvc_start_streaming(devh, byref(ctrl), callback, None, 0)
    if res < 0:
        raise RuntimeError(f"uvc_start_streaming failed with code {res}")

    frames: List[np.ndarray] = []
    print("Streaming started. Press Ctrl+C to stop early.")
    if live_preview:
        print("Live preview enabled (Celsius min/max overlay).")
        print("Conversion assumption: Lepton 3.5 TLinear ON at 0.01 K resolution.")
        print(
            "Hotspot thresholds: "
            f"abs={threshold_state.absolute_threshold}C "
            f"delta={threshold_state.delta_threshold}C "
            f"sigma={threshold_state.sigma_threshold} "
            f"mode={threshold_state.threshold_mode}"
        )
        print(
            "Display window: "
            f"mode={display_state.mode} "
            f"pct={display_state.pct_low:.1f}-{display_state.pct_high:.1f} "
            f"fixed=({display_state.fixed_min_c},{display_state.fixed_max_c})"
        )
        try:
            plt, fig, image, marker, text = init_live_preview(preview_colormap)

            def on_key(event):
                key = event.key
                if key is None:
                    return
                changed = False
                if key == "[":
                    if threshold_state.absolute_threshold is not None:
                        threshold_state.absolute_threshold = max(0.0, threshold_state.absolute_threshold - 10.0)
                        changed = True
                elif key == "]":
                    base = threshold_state.absolute_threshold if threshold_state.absolute_threshold is not None else WILDFIRE_ABS_THRESHOLD_C
                    threshold_state.absolute_threshold = base + 10.0
                    changed = True
                elif key == ",":
                    if threshold_state.delta_threshold is not None:
                        threshold_state.delta_threshold = max(0.0, threshold_state.delta_threshold - 2.0)
                        changed = True
                elif key == ".":
                    base = threshold_state.delta_threshold if threshold_state.delta_threshold is not None else WILDFIRE_DELTA_THRESHOLD_C
                    threshold_state.delta_threshold = base + 2.0
                    changed = True
                elif key == "-":
                    if threshold_state.sigma_threshold is not None:
                        threshold_state.sigma_threshold = max(0.0, threshold_state.sigma_threshold - 0.25)
                        changed = True
                elif key in ("+", "="):
                    base = threshold_state.sigma_threshold if threshold_state.sigma_threshold is not None else 2.5
                    threshold_state.sigma_threshold = base + 0.25
                    changed = True
                elif key.lower() == "m":
                    threshold_state.threshold_mode = "any" if threshold_state.threshold_mode == "all" else "all"
                    changed = True
                elif key == "f":
                    if preview_runtime["last_frame_c"] is not None:
                        nudge_display_floor(display_state, preview_runtime["last_frame_c"], -1.0)
                        changed = True
                elif key == "F":
                    if preview_runtime["last_frame_c"] is not None:
                        nudge_display_floor(display_state, preview_runtime["last_frame_c"], 1.0)
                        changed = True
                elif key == "c":
                    if preview_runtime["last_frame_c"] is not None:
                        nudge_display_ceiling(display_state, preview_runtime["last_frame_c"], -1.0)
                        changed = True
                elif key == "C":
                    if preview_runtime["last_frame_c"] is not None:
                        nudge_display_ceiling(display_state, preview_runtime["last_frame_c"], 1.0)
                        changed = True
                elif key.lower() == "v":
                    display_state.mode = cycle_display_mode(display_state.mode)
                    display_state.manual_floor_c = None
                    display_state.manual_ceiling_c = None
                    changed = True
                elif key.lower() == "r":
                    display_state.manual_floor_c = None
                    display_state.manual_ceiling_c = None
                    changed = True

                if changed and preview_runtime["last_frame_c"] is not None:
                    update_live_preview(
                        plt,
                        fig,
                        image,
                        marker,
                        text,
                        int(preview_runtime["last_idx"]),
                        preview_runtime["last_frame_c"],
                        threshold_state,
                        display_state,
                    )

            fig.canvas.mpl_connect("key_press_event", on_key)
        except Exception as exc:
            print(f"Live preview disabled: failed to initialize plotting window ({exc})", file=sys.stderr)
            live_preview = False

    try:
        while True:
            elapsed = time.monotonic() - capture_start_monotonic
            if duration_sec is not None and elapsed >= duration_sec:
                print(f"Stopping: duration reached ({duration_sec:.2f}s)")
                break
            if max_frames is not None and len(frames) >= max_frames:
                print(f"Stopping: frame limit reached ({max_frames})")
                break

            try:
                frame, ts = frame_queue.get(timeout=0.5)
            except Empty:
                continue

            frames.append(frame)
            frame_times.append(ts)
            frame_idx = len(frames) - 1

            if live_preview and plt is not None and fig is not None and image is not None and marker is not None and text is not None:
                frame_celsius = raw_to_celsius(frame)
                frame_min_c = float(np.min(frame_celsius))
                frame_max_c = float(np.max(frame_celsius))
                if display_state.global_min_c is None or frame_min_c < display_state.global_min_c:
                    display_state.global_min_c = frame_min_c
                if display_state.global_max_c is None or frame_max_c > display_state.global_max_c:
                    display_state.global_max_c = frame_max_c
                preview_runtime["last_idx"] = frame_idx
                preview_runtime["last_frame_c"] = frame_celsius
                still_open = update_live_preview(
                    plt,
                    fig,
                    image,
                    marker,
                    text,
                    frame_idx,
                    frame_celsius,
                    threshold_state,
                    display_state,
                )
                if not still_open:
                    print("Live preview window closed; capture will continue without preview.")
                    live_preview = False

            if len(frames) == 1 or len(frames) % max(1, int(nominal_fps)) == 0:
                print(f"Captured {len(frames)} frame(s)")

    except KeyboardInterrupt:
        print("Capture interrupted by user.")
    finally:
        uvc.libuvc.uvc_stop_streaming(devh)
        if plt is not None and fig is not None and plt.fignum_exists(fig.number):
            plt.close(fig)

    capture_end_monotonic = time.monotonic()
    total_duration = max(0.0, capture_end_monotonic - capture_start_monotonic)
    return frames, frame_times, total_duration


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture FLIR Lepton thermal frames via libuvc/ctypes and save as .npy",
    )
    parser.add_argument("--output-dir", default=".", help="Directory for output .npy + metadata .json")
    parser.add_argument("--prefix", default="lepton_frames", help="Output filename prefix")
    parser.add_argument("--max-frames", type=int, default=None, help="Stop after this many frames")
    parser.add_argument("--duration-sec", type=float, default=None, help="Stop after this many seconds")
    parser.add_argument("--vid", type=parse_hex_or_int, default=None, help="Manual camera VID override (int or hex, e.g. 0x1e4e)")
    parser.add_argument("--pid", type=parse_hex_or_int, default=None, help="Manual camera PID override (int or hex, e.g. 0x0100)")
    parser.add_argument(
        "--print-device-info",
        action="store_true",
        help="Print detected device info and advertised stream formats",
    )
    parser.add_argument(
        "--live-preview",
        action="store_true",
        help="Show live playback window with per-frame min/max Celsius while capturing",
    )
    parser.add_argument(
        "--preview-colormap",
        default="inferno",
        help="Matplotlib colormap for live preview (used with --live-preview)",
    )
    parser.add_argument(
        "--preview-display-mode",
        choices=DISPLAY_MODE_CHOICES,
        default="percentile",
        help="Live preview display window mode: percentile|minmax|fixed|global",
    )
    parser.add_argument(
        "--preview-display-pct-low",
        type=float,
        default=1.0,
        help="Low percentile for preview-display-mode=percentile (default: 1.0)",
    )
    parser.add_argument(
        "--preview-display-pct-high",
        type=float,
        default=99.0,
        help="High percentile for preview-display-mode=percentile (default: 99.0)",
    )
    parser.add_argument(
        "--preview-fixed-min-c",
        type=float,
        default=None,
        help="Fixed display floor in Celsius for preview-display-mode=fixed",
    )
    parser.add_argument(
        "--preview-fixed-max-c",
        type=float,
        default=None,
        help="Fixed display ceiling in Celsius for preview-display-mode=fixed",
    )
    parser.add_argument(
        "--hotspot-profile",
        choices=["none", "wildfire"],
        default="wildfire",
        help="Hotspot threshold preset for live preview focus",
    )
    parser.add_argument("--hotspot-abs-threshold", type=float, default=None, help="Hotspot absolute threshold in Celsius")
    parser.add_argument("--hotspot-delta-threshold", type=float, default=None, help="Hotspot threshold above frame median in Celsius")
    parser.add_argument("--hotspot-sigma-threshold", type=float, default=None, help="Hotspot threshold as mean + sigma*std")
    parser.add_argument(
        "--hotspot-threshold-mode",
        choices=["any", "all"],
        default=WILDFIRE_THRESHOLD_MODE,
        help="How to combine hotspot thresholds when more than one is enabled",
    )

    args = parser.parse_args()

    try:
        ensure_stop_condition(args.max_frames, args.duration_sec)
    except ValueError as exc:
        print(f"Argument error: {exc}", file=sys.stderr)
        return 2

    if (args.vid is None) ^ (args.pid is None):
        print("Argument error: provide both --vid and --pid together for manual override.", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = create_filename(output_dir, args.prefix)
    metadata_path = output_path.with_suffix(".json")
    hotspot_thresholds = resolve_hotspot_thresholds(
        profile=args.hotspot_profile,
        absolute_threshold=args.hotspot_abs_threshold,
        delta_threshold=args.hotspot_delta_threshold,
        sigma_threshold=args.hotspot_sigma_threshold,
        threshold_mode=args.hotspot_threshold_mode,
    )
    preview_display = build_display_state(
        mode=args.preview_display_mode,
        pct_low=args.preview_display_pct_low,
        pct_high=args.preview_display_pct_high,
        fixed_min_c=args.preview_fixed_min_c,
        fixed_max_c=args.preview_fixed_max_c,
    )

    try:
        uvc = load_uvc_module()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    ctx = POINTER(uvc.uvc_context)()
    dev = POINTER(uvc.uvc_device)()
    devh = POINTER(uvc.uvc_device_handle)()
    ctrl = uvc.uvc_stream_ctrl()

    start_wall_clock = datetime.now(timezone.utc)

    print("Initializing UVC context...")
    res = uvc.libuvc.uvc_init(byref(ctx), 0)
    if res < 0:
        print(f"uvc_init failed with code {res}", file=sys.stderr)
        return 1

    try:
        try:
            dev, used_vid, used_pid = discover_device(uvc, ctx, args.vid, args.pid)
            print(f"Found device VID=0x{used_vid:04x} PID=0x{used_pid:04x}")

            res = uvc.libuvc.uvc_open(dev, byref(devh))
            if res < 0:
                print(f"uvc_open failed with code {res}", file=sys.stderr)
                print("Hint: on macOS, try running with sudo if libusb access is denied.", file=sys.stderr)
                return 1

            print("Device opened.")
            if args.print_device_info:
                uvc.print_device_info(devh)
                uvc.print_device_formats(devh)

            frame_formats = uvc.uvc_get_frame_formats_by_guid(devh, uvc.VS_FMT_GUID_Y16)
            if not frame_formats:
                print("Device does not advertise Y16 frame format required for thermal capture.", file=sys.stderr)
                return 1

            selected_format = frame_formats[0]
            width = int(selected_format.wWidth)
            height = int(selected_format.wHeight)
            nominal_fps = float(int(1e7 / selected_format.dwDefaultFrameInterval))

            uvc.libuvc.uvc_get_stream_ctrl_format_size(
                devh,
                byref(ctrl),
                uvc.UVC_FRAME_FORMAT_Y16,
                selected_format.wWidth,
                selected_format.wHeight,
                int(1e7 / selected_format.dwDefaultFrameInterval),
            )

            print(f"Using Y16 stream {width}x{height} @ nominal {nominal_fps:.2f} fps")
            frames, frame_times, duration = capture_frames(
                uvc,
                devh,
                ctrl,
                args.max_frames,
                args.duration_sec,
                nominal_fps,
                args.live_preview,
                args.preview_colormap,
                hotspot_thresholds,
                preview_display,
            )

            if not frames:
                print("No frames captured. Nothing saved.", file=sys.stderr)
                return 1

            stack = np.stack(frames, axis=0)
            np.save(output_path, stack)

            estimated_fps = (len(frames) / duration) if duration > 0 else 0.0
            start_monotonic = frame_times[0] if frame_times else None
            rel_frame_times = [t - start_monotonic for t in frame_times] if start_monotonic is not None else []

            metadata = {
                "capture_start_utc": start_wall_clock.isoformat(),
                "capture_end_utc": datetime.now(timezone.utc).isoformat(),
                "duration_sec": duration,
                "frame_count": int(stack.shape[0]),
                "resolution": [int(stack.shape[2]), int(stack.shape[1])],
                "dtype": str(stack.dtype),
                "nominal_fps": nominal_fps,
                "estimated_fps": estimated_fps,
                "stop_conditions": {
                    "max_frames": args.max_frames,
                    "duration_sec": args.duration_sec,
                },
                "camera": {
                    "vid": f"0x{used_vid:04x}",
                    "pid": f"0x{used_pid:04x}",
                    "format": "Y16",
                },
                "hotspot_thresholds": {
                    "profile": args.hotspot_profile,
                    "absolute_threshold_c": hotspot_thresholds.absolute_threshold,
                    "delta_threshold_c": hotspot_thresholds.delta_threshold,
                    "sigma_threshold": hotspot_thresholds.sigma_threshold,
                    "mode": hotspot_thresholds.threshold_mode,
                },
                "frame_time_offsets_sec": rel_frame_times,
                "frames_file": output_path.name,
            }
            save_session_metadata(metadata_path, metadata)

            print("Capture complete.")
            print(f"Saved frames:   {output_path}")
            print(f"Saved metadata: {metadata_path}")
            print(f"Frame count:    {metadata['frame_count']}")
            print(f"Duration (s):   {duration:.3f}")
            print(f"Estimated fps:  {estimated_fps:.3f}")

            return 0

        finally:
            if bool(devh):
                uvc.libuvc.uvc_close(devh)
            if bool(dev):
                uvc.libuvc.uvc_unref_device(dev)
    finally:
        uvc.libuvc.uvc_exit(ctx)


if __name__ == "__main__":
    raise SystemExit(main())
