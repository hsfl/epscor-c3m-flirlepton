#!/usr/bin/env python3
"""Capture FLIR Lepton thermal frames via libuvc and save as .npy stack."""

import argparse
import json
import os
import re
import sys
import time
from ctypes import CFUNCTYPE, POINTER, byref, c_uint16, c_void_p, cast
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Dict, List, Optional, Tuple

import numpy as np


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


def capture_frames(
    uvc,
    devh,
    ctrl,
    max_frames: Optional[int],
    duration_sec: Optional[float],
    nominal_fps: float,
) -> Tuple[List[np.ndarray], List[float], float]:
    frame_queue: Queue = Queue(maxsize=8)
    capture_start_monotonic = time.monotonic()
    frame_times: List[float] = []

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

            if len(frames) == 1 or len(frames) % max(1, int(nominal_fps)) == 0:
                print(f"Captured {len(frames)} frame(s)")

    except KeyboardInterrupt:
        print("Capture interrupted by user.")
    finally:
        uvc.libuvc.uvc_stop_streaming(devh)

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
