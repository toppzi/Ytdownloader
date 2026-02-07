#!/usr/bin/env python3
"""
YouTube Playlist to MP3 Downloader – simple GUI to download all tracks from a
YouTube playlist as MP3 files using yt-dlp.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

# tkinter is in the stdlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext


# Placeholder shown in URL entry until user focuses
PLACEHOLDER_URL = "https://music.youtube.com/playlist?list=..."

# Config file for persisting last output directory
def _config_path() -> Path:
    p = Path.home() / ".config" / "yt-playlist-mp3"
    p.mkdir(parents=True, exist_ok=True)
    return p / "config.json"


def load_config() -> dict:
    try:
        with open(_config_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(data: dict) -> None:
    with open(_config_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# Validate YouTube / YouTube Music playlist and video URLs
def is_youtube_url(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    patterns = [
        # youtube.com
        r"https?://(www\.)?youtube\.com/playlist\?list=[\w-]+",
        r"https?://(www\.)?youtube\.com/watch\?v=[\w-]+(&list=[\w-]+)?",
        r"https?://youtu\.be/[\w-]+",
        # music.youtube.com (YouTube Music)
        r"https?://music\.youtube\.com/playlist\?list=[\w-]+",
        r"https?://music\.youtube\.com/watch\?v=[\w-]+(&list=[\w-]+)?",
    ]
    return any(re.match(p, text) for p in patterns)


def get_yt_dlp_cmd():
    """Return list of command parts to run yt-dlp: [exe] or [python, '-m', 'yt_dlp']."""
    exe = "yt-dlp"
    if sys.platform == "win32":
        exe = "yt-dlp.exe"
    # Check PATH
    for p in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(p, exe)
        if os.path.isfile(candidate):
            return [candidate]
    # Same dir as script
    script_dir = Path(__file__).resolve().parent
    candidate = script_dir / exe
    if candidate.is_file():
        return [str(candidate)]
    # Fallback: run as module (works when installed via pip but exe not on PATH)
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        pass
    return [exe]


def get_js_runtime_args():
    """Return yt-dlp args for a JS runtime. Deno is default; if missing, use node or bun."""
    if shutil.which("deno"):
        return []
    if shutil.which("node"):
        return ["--js-runtimes", "node"]
    if shutil.which("bun"):
        return ["--js-runtimes", "bun"]
    return []


class PlaylistMP3App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("YouTube Playlist → MP3")
        self.root.minsize(520, 420)
        self.root.geometry("620x500")

        self.download_running = False
        self.process = None
        self.yt_dlp_cmd = get_yt_dlp_cmd()

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # Playlist URL
        ttk.Label(main, text="Playlist or video URL:").pack(anchor=tk.W)
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(main, textvariable=self.url_var, width=70)
        url_entry.pack(fill=tk.X, pady=(2, 10))
        url_entry.delete(0, tk.END)
        url_entry.insert(0, PLACEHOLDER_URL)
        url_entry.bind("<FocusIn>", lambda e: self._clear_placeholder(url_entry))

        # Output folder (restore last used)
        row = ttk.Frame(main)
        row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(row, text="Save to:").pack(side=tk.LEFT, padx=(0, 8))
        self.path_var = tk.StringVar(value=load_config().get("output_dir", ""))
        path_entry = ttk.Entry(row, textvariable=self.path_var, width=50)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(row, text="Browse…", command=self._browse).pack(side=tk.LEFT)

        # Bitrate (kbps)
        bitrate_row = ttk.Frame(main)
        bitrate_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(bitrate_row, text="Bitrate:").pack(side=tk.LEFT, padx=(0, 8))
        self.bitrate_var = tk.StringVar(value="320 kbps")
        bitrate_combo = ttk.Combobox(
            bitrate_row,
            textvariable=self.bitrate_var,
            values=["128 kbps", "192 kbps", "256 kbps", "320 kbps", "Best (VBR)"],
            state="readonly",
            width=14,
        )
        bitrate_combo.pack(side=tk.LEFT)

        # Progress bar (updated from yt-dlp output)
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            main, variable=self.progress_var, maximum=100.0, mode="determinate"
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 8))

        # Buttons
        btn_row = ttk.Frame(main)
        btn_row.pack(fill=tk.X, pady=(4, 8))
        self.btn_download = ttk.Button(
            btn_row, text="Download as MP3", command=self._start_download
        )
        self.btn_download.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_stop = ttk.Button(btn_row, text="Stop", command=self._stop_download, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT)

        # Progress / log
        log_row = ttk.Frame(main)
        log_row.pack(fill=tk.X)
        ttk.Label(log_row, text="Log:").pack(side=tk.LEFT)
        ttk.Button(log_row, text="Clear", command=self._clear_log).pack(side=tk.RIGHT)
        self.log = scrolledtext.ScrolledText(
            main, height=14, wrap=tk.WORD, state=tk.DISABLED, font="TkFixedFont",
        )
        self.log.pack(fill=tk.BOTH, expand=True, pady=(2, 0))

        self._log("Paste a YouTube or YouTube Music playlist/video URL, choose a folder, then click Download as MP3.")
        self._log("Requires: yt-dlp and ffmpeg on PATH (or in this folder).")
        self._log("")

    def _clear_placeholder(self, entry: ttk.Entry):
        if entry.get().strip() == PLACEHOLDER_URL:
            entry.delete(0, tk.END)

    def _browse(self):
        path = filedialog.askdirectory(title="Choose folder for MP3 files")
        if path:
            self.path_var.set(path)
            save_config(load_config() | {"output_dir": path})

    def _log(self, msg: str):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log.configure(state=tk.NORMAL)
        self.log.delete(1.0, tk.END)
        self.log.configure(state=tk.DISABLED)

    def _progress_reset(self):
        """Reset progress bar to indeterminate (unknown progress) at start."""
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start(8)

    def _progress_set_percent(self, value: float):
        """Set progress bar to a 0–100 percentage (determinate)."""
        try:
            self.progress_bar.stop()
        except tk.TclError:
            pass
        self.progress_bar.configure(mode="determinate")
        self.progress_var.set(max(0.0, min(100.0, value)))

    def _progress_done(self):
        """Stop progress bar and set to 100%."""
        try:
            self.progress_bar.stop()
        except tk.TclError:
            pass
        self.progress_bar.configure(mode="determinate")
        self.progress_var.set(100.0)

    def _parse_progress_line(self, line: str) -> Optional[float]:
        """Extract download percentage from a yt-dlp progress line. Returns 0–100 or None."""
        # e.g. [download] 45.2% of 5.00MiB at 1.20MiB/s ETA 00:03
        # e.g. [download] 100% of 1.20MiB in 00:00
        m = re.search(r"\[download\]\s*(\d+(?:\.\d+)?)\s*%", line)
        if m:
            return float(m.group(1))
        return None

    def _start_download(self):
        url = (self.url_var.get() or "").strip()
        out = (self.path_var.get() or "").strip()

        if not url or url == PLACEHOLDER_URL:
            messagebox.showwarning("Missing URL", "Please enter a YouTube or YouTube Music playlist or video URL.")
            return
        if not is_youtube_url(url):
            messagebox.showwarning("Invalid URL", "That doesn’t look like a valid YouTube or YouTube Music URL.")
            return
        if not out:
            messagebox.showwarning("Missing folder", "Please choose a folder to save the MP3 files.")
            return
        if not os.path.isdir(out):
            messagebox.showerror("Invalid folder", f"Folder does not exist:\n{out}")
            return

        save_config(load_config() | {"output_dir": out})

        self.download_running = True
        self.btn_download.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self._clear_log()
        self._progress_reset()
        self._log("Starting download…")
        self._log("")

        bitrate = self.bitrate_var.get().strip()
        thread = threading.Thread(target=self._run_download, args=(url, out, bitrate), daemon=True)
        thread.start()

    def _run_download(self, url: str, output_dir: str, bitrate: str):
        # Map display label to yt-dlp --audio-quality value (K = CBR kbps, 0 = best VBR)
        quality_map = {
            "128 kbps": "128K",
            "192 kbps": "192K",
            "256 kbps": "256K",
            "320 kbps": "320K",
            "Best (VBR)": "0",
        }
        quality = quality_map.get(bitrate, "320K")
        # Filename: "01 - Artist - Title.mp3" with playlist order; %(playlist_index)s is 1,2,... for playlist/single
        out_tmpl = os.path.join(output_dir, "%(playlist_index)02d - %(artist,Unknown)s - %(title)s.%(ext)s")
        cmd = list(self.yt_dlp_cmd) + get_js_runtime_args() + [
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", quality,
            "-o", out_tmpl,
            "--embed-metadata",
            "--newline",
            "--progress",
            "--no-mtime",
            url,
        ]
        returncode = 0
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in self.process.stdout:
                if not self.download_running:
                    self.process.terminate()
                    break
                line = line.rstrip()
                if line:
                    self.root.after(0, lambda l=line: self._log(l))
                    percent = self._parse_progress_line(line)
                    if percent is not None:
                        self.root.after(0, lambda p=percent: self._progress_set_percent(p))
            returncode = self.process.wait()
        except FileNotFoundError:
            returncode = -1
            self.root.after(0, lambda: self._log(
                "Error: yt-dlp not found. Run in terminal: pip install -r requirements.txt\n"
                "Then ensure ffmpeg is installed (e.g. sudo dnf install ffmpeg)."
            ))
        except Exception as e:
            self.root.after(0, lambda: self._log(f"Error: {e}"))
            returncode = -1
        finally:
            self.root.after(0, lambda: self._download_finished(returncode))

    def _stop_download(self):
        self.download_running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self._log("Stopping…")

    def _download_finished(self, returncode: int = 0):
        self.download_running = False
        self.process = None
        self.btn_download.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)
        self.root.after(0, self._progress_done)
        if returncode == 0:
            self._log("Download complete.")
        else:
            self._log(f"Download failed (exit code {returncode}).")

    def run(self):
        self.root.mainloop()


def main():
    app = PlaylistMP3App()
    app.run()


if __name__ == "__main__":
    main()
