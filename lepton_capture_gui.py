#!/usr/bin/env python3
"""Quick GUI preview + rename tool for Lepton .npy captures."""

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from tkinter import END, LEFT, RIGHT, StringVar, Tk, messagebox
from tkinter import filedialog
import tkinter as tk


FILENAME_TS_PATTERN = re.compile(r".*_(\d{8})_(\d{6})(?:_\d+)?$")


@dataclass
class CaptureInfo:
    path: Path
    frame_count: int
    height: int
    width: int
    dtype: str
    min_raw: float
    max_raw: float
    capture_start_utc: Optional[str]
    capture_end_utc: Optional[str]
    estimated_fps: Optional[float]


class CapturePreviewApp:
    def __init__(self, root: Tk, capture_dir: Path, colormap: str = "inferno") -> None:
        self.root = root
        self.capture_dir = capture_dir
        self.colormap = colormap

        self.npy_files: List[Path] = []
        self.current_file_index = -1
        self.current_frames: Optional[np.ndarray] = None
        self.current_info: Optional[CaptureInfo] = None
        self.current_image = None
        self.is_playing = False
        self.play_job = None

        self.status_var = StringVar()
        self.meta_var = StringVar()
        self.frame_var = StringVar(value="Frame: -")
        self.play_button_var = StringVar(value="Play")
        self.fps_var = StringVar(value="8.0")

        self._build_ui()
        self.refresh_file_list()

    def _build_ui(self) -> None:
        self.root.title("Lepton Capture Preview + Rename")
        self.root.geometry("1200x720")

        root_frame = tk.Frame(self.root)
        root_frame.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(root_frame, padx=8, pady=8)
        left.pack(side=LEFT, fill=tk.Y)

        right = tk.Frame(root_frame, padx=8, pady=8)
        right.pack(side=RIGHT, fill=tk.BOTH, expand=True)

        top_row = tk.Frame(left)
        top_row.pack(fill=tk.X, pady=(0, 6))

        tk.Button(top_row, text="Open Folder", command=self.open_folder).pack(side=LEFT)
        tk.Button(top_row, text="Refresh", command=self.refresh_file_list).pack(side=LEFT, padx=(6, 0))

        self.listbox = tk.Listbox(left, width=50, height=30)
        self.listbox.pack(fill=tk.Y, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        nav_row = tk.Frame(left)
        nav_row.pack(fill=tk.X, pady=(6, 6))
        tk.Button(nav_row, text="Prev", command=self.prev_file).pack(side=LEFT)
        tk.Button(nav_row, text="Next", command=self.next_file).pack(side=LEFT, padx=(6, 0))

        tk.Label(left, textvariable=self.status_var, justify=LEFT, anchor="w", wraplength=360).pack(fill=tk.X, pady=(4, 0))

        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("Frame Preview")
        self.ax.set_axis_off()
        self.canvas = FigureCanvasTkAgg(self.figure, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        control_row = tk.Frame(right)
        control_row.pack(fill=tk.X, pady=(8, 4))

        self.frame_slider = tk.Scale(
            control_row,
            from_=0,
            to=0,
            orient=tk.HORIZONTAL,
            command=self.on_frame_change,
            showvalue=True,
            length=520,
            label="Frame",
        )
        self.frame_slider.pack(side=LEFT, fill=tk.X, expand=True)

        tk.Label(control_row, textvariable=self.frame_var).pack(side=LEFT, padx=(8, 0))
        tk.Button(control_row, textvariable=self.play_button_var, command=self.toggle_play).pack(side=LEFT, padx=(8, 0))
        tk.Label(control_row, text="FPS").pack(side=LEFT, padx=(8, 2))
        tk.Entry(control_row, textvariable=self.fps_var, width=5).pack(side=LEFT)

        tk.Label(right, textvariable=self.meta_var, justify=LEFT, anchor="w").pack(fill=tk.X, pady=(2, 8))

        rename_row = tk.Frame(right)
        rename_row.pack(fill=tk.X)
        tk.Label(rename_row, text="Rename selected capture to:").pack(side=LEFT)
        self.rename_entry = tk.Entry(rename_row)
        self.rename_entry.pack(side=LEFT, fill=tk.X, expand=True, padx=(8, 8))
        tk.Button(rename_row, text="Rename", command=self.rename_selected).pack(side=LEFT)

        self.root.bind("<Left>", lambda _e: self.prev_file())
        self.root.bind("<Right>", lambda _e: self.next_file())
        self.root.bind("<Return>", lambda _e: self.rename_selected())

    def open_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=str(self.capture_dir))
        if not selected:
            return
        self.capture_dir = Path(selected)
        self.refresh_file_list()

    def refresh_file_list(self) -> None:
        self.stop_playback()
        self.npy_files = sorted(self.capture_dir.glob("*.npy"))
        self.listbox.delete(0, END)
        for p in self.npy_files:
            self.listbox.insert(END, p.name)

        if not self.npy_files:
            self.current_file_index = -1
            self.current_frames = None
            self.current_info = None
            self.meta_var.set("No .npy files found in this folder.")
            self.status_var.set(f"Folder: {self.capture_dir}")
            self.frame_var.set("Frame: -")
            self.ax.clear()
            self.ax.set_title("Frame Preview")
            self.ax.set_axis_off()
            self.canvas.draw_idle()
            return

        self.status_var.set(f"Folder: {self.capture_dir} ({len(self.npy_files)} files)")
        target = 0 if self.current_file_index < 0 else min(self.current_file_index, len(self.npy_files) - 1)
        self.select_file(target)

    def select_file(self, index: int) -> None:
        if index < 0 or index >= len(self.npy_files):
            return

        self.stop_playback()
        self.current_file_index = index
        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(index)
        self.listbox.activate(index)
        self.listbox.see(index)

        path = self.npy_files[index]
        try:
            frames = self.load_frames(path)
        except Exception as exc:
            self.current_frames = None
            self.current_info = None
            self.meta_var.set(f"Failed to load {path.name}: {exc}")
            return

        self.current_frames = frames
        self.current_info = self.build_capture_info(path, frames)
        if self.current_info.estimated_fps is not None:
            self.fps_var.set(f"{self.current_info.estimated_fps:.2f}")

        self.rename_entry.delete(0, END)
        self.rename_entry.insert(0, path.stem)

        self.frame_slider.configure(to=max(0, frames.shape[0] - 1))
        self.frame_slider.set(0)
        self.show_frame(0)
        self.update_metadata_label()

    def prev_file(self) -> None:
        if self.current_file_index > 0:
            self.select_file(self.current_file_index - 1)

    def next_file(self) -> None:
        if self.current_file_index < len(self.npy_files) - 1:
            self.select_file(self.current_file_index + 1)

    def _on_select(self, _event) -> None:
        selection = self.listbox.curselection()
        if selection:
            self.select_file(int(selection[0]))

    def on_frame_change(self, value: str) -> None:
        if self.current_frames is None:
            return
        idx = int(float(value))
        self.show_frame(idx)

    def toggle_play(self) -> None:
        if self.current_frames is None:
            return

        if self.is_playing:
            self.stop_playback()
            return

        self.is_playing = True
        self.play_button_var.set("Pause")
        self._schedule_next_frame()

    def stop_playback(self) -> None:
        self.is_playing = False
        self.play_button_var.set("Play")
        if self.play_job is not None:
            self.root.after_cancel(self.play_job)
            self.play_job = None

    def _schedule_next_frame(self) -> None:
        if not self.is_playing or self.current_frames is None:
            return

        delay_ms = max(1, int(1000.0 / self._get_playback_fps()))
        self.play_job = self.root.after(delay_ms, self._play_tick)

    def _play_tick(self) -> None:
        self.play_job = None
        if not self.is_playing or self.current_frames is None:
            return

        max_frame = self.current_frames.shape[0] - 1
        current = int(self.frame_slider.get())
        next_idx = current + 1 if current < max_frame else 0
        self.frame_slider.set(next_idx)
        self._schedule_next_frame()

    def _get_playback_fps(self) -> float:
        try:
            fps = float(self.fps_var.get())
        except (TypeError, ValueError):
            fps = 8.0
            self.fps_var.set("8.0")
        return min(max(fps, 0.5), 60.0)

    def show_frame(self, index: int) -> None:
        if self.current_frames is None:
            return

        index = max(0, min(index, self.current_frames.shape[0] - 1))
        frame = self.current_frames[index]

        self.ax.clear()
        frame_min = float(frame.min())
        frame_max = float(frame.max())
        self.current_image = self.ax.imshow(frame, cmap=self.colormap)
        self.ax.set_title(f"{self.npy_files[self.current_file_index].name} | frame {index}")
        self.ax.set_axis_off()

        self.frame_var.set(f"Frame: {index} | min {frame_min:.1f} | max {frame_max:.1f}")
        self.canvas.draw_idle()

    def rename_selected(self) -> None:
        if self.current_file_index < 0 or self.current_file_index >= len(self.npy_files):
            return

        old_path = self.npy_files[self.current_file_index]
        new_stem = self.rename_entry.get().strip()
        if not new_stem:
            messagebox.showerror("Invalid name", "Filename cannot be empty.")
            return
        if "/" in new_stem or "\\" in new_stem:
            messagebox.showerror("Invalid name", "Use a base filename only, without path separators.")
            return

        new_path = old_path.with_name(f"{new_stem}.npy")
        if new_path == old_path:
            return
        if new_path.exists():
            messagebox.showerror("Name exists", f"Target already exists: {new_path.name}")
            return

        old_json = old_path.with_suffix(".json")
        new_json = new_path.with_suffix(".json")
        if old_json.exists() and new_json.exists() and old_json != new_json:
            messagebox.showerror("JSON conflict", f"Cannot rename because {new_json.name} already exists.")
            return

        try:
            old_path.rename(new_path)
            if old_json.exists():
                old_json.rename(new_json)
        except Exception as exc:
            messagebox.showerror("Rename failed", str(exc))
            return

        self.refresh_file_list()
        match_index = next((i for i, p in enumerate(self.npy_files) if p == new_path), None)
        if match_index is not None:
            self.select_file(match_index)

    @staticmethod
    def load_frames(path: Path) -> np.ndarray:
        data = np.load(path)
        if not isinstance(data, np.ndarray):
            raise ValueError("Loaded object is not a NumPy ndarray")
        if data.ndim != 3:
            raise ValueError(f"Expected shape (N, H, W); got {data.shape}")
        if data.shape[0] < 1:
            raise ValueError("Capture has no frames")
        return data

    def build_capture_info(self, path: Path, frames: np.ndarray) -> CaptureInfo:
        metadata = self.load_metadata(path)
        return CaptureInfo(
            path=path,
            frame_count=int(frames.shape[0]),
            height=int(frames.shape[1]),
            width=int(frames.shape[2]),
            dtype=str(frames.dtype),
            min_raw=float(frames.min()),
            max_raw=float(frames.max()),
            capture_start_utc=metadata.get("capture_start_utc") if metadata else None,
            capture_end_utc=metadata.get("capture_end_utc") if metadata else None,
            estimated_fps=self._safe_float(metadata.get("estimated_fps")) if metadata else None,
        )

    def update_metadata_label(self) -> None:
        if self.current_info is None:
            self.meta_var.set("")
            return

        info = self.current_info
        lines = [
            f"File: {info.path.name}",
            f"Frames: {info.frame_count} | Shape: {info.height}x{info.width} | dtype: {info.dtype}",
            f"Raw range: {info.min_raw:.1f} to {info.max_raw:.1f}",
        ]

        local_start = self._to_local_time(info.capture_start_utc)
        local_end = self._to_local_time(info.capture_end_utc)
        parsed_name_ts = self._parse_filename_timestamp(info.path.stem)

        if local_start:
            lines.append(f"Start (local): {local_start}")
        elif parsed_name_ts:
            lines.append(f"Start (from filename, local): {parsed_name_ts}")
        else:
            lines.append("Start: unavailable")

        if local_end:
            lines.append(f"End (local): {local_end}")
        if info.estimated_fps is not None:
            lines.append(f"Estimated FPS: {info.estimated_fps:.3f}")

        sidecar = info.path.with_suffix(".json")
        lines.append(f"Metadata JSON: {'present' if sidecar.exists() else 'missing'}")

        self.meta_var.set("\n".join(lines))

    @staticmethod
    def load_metadata(npy_path: Path) -> Optional[dict]:
        sidecar = npy_path.with_suffix(".json")
        if not sidecar.exists():
            return None
        try:
            with sidecar.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_filename_timestamp(stem: str) -> Optional[str]:
        match = FILENAME_TS_PATTERN.match(stem)
        if not match:
            return None
        date_part, time_part = match.groups()
        try:
            dt_utc = datetime.strptime(f"{date_part}{time_part}", "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return dt_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        except ValueError:
            return None

    @staticmethod
    def _to_local_time(iso_ts: Optional[str]) -> Optional[str]:
        if not iso_ts:
            return None
        try:
            dt = datetime.fromisoformat(iso_ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        except ValueError:
            return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quick preview + rename GUI for Lepton .npy captures")
    parser.add_argument(
        "capture_dir",
        nargs="?",
        default="captures",
        help="Directory containing .npy captures (default: captures)",
    )
    parser.add_argument("--colormap", default="inferno", help="Matplotlib colormap for preview")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    capture_dir = Path(args.capture_dir).expanduser().resolve()
    if not capture_dir.exists() or not capture_dir.is_dir():
        raise SystemExit(f"Capture directory not found: {capture_dir}")

    plt.style.use("fast")

    root = Tk()
    app = CapturePreviewApp(root, capture_dir, colormap=args.colormap)
    _ = app
    root.mainloop()


if __name__ == "__main__":
    main()
