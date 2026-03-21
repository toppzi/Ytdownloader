"""
Shared helpers for GUI and CLI: config, URL checks, yt-dlp command building, progress parsing.
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Bitrate labels (GUI/CLI) → yt-dlp --audio-quality (K = CBR kbps, 0 = best VBR)
BITRATE_LABELS = ("128 kbps", "192 kbps", "256 kbps", "320 kbps", "Best (VBR)")
QUALITY_MAP = {
    "128 kbps": "128K",
    "192 kbps": "192K",
    "256 kbps": "256K",
    "320 kbps": "320K",
    "Best (VBR)": "0",
}


def config_path() -> Path:
    p = Path.home() / ".config" / "yt-playlist-mp3"
    p.mkdir(parents=True, exist_ok=True)
    return p / "config.json"


def ensure_output_dir(path: str) -> str:
    """
    Normalize path (expand user, absolute). Create the directory and any missing parents if needed.
    Raises NotADirectoryError if the path exists but is not a directory.
    Raises OSError on permission or other filesystem errors.
    """
    p = Path(os.path.abspath(os.path.expanduser((path or "").strip())))
    if p.exists() and not p.is_dir():
        raise NotADirectoryError(f"Not a folder: {p}")
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def load_config() -> dict:
    try:
        with open(config_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(data: dict) -> None:
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def is_youtube_url(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    patterns = [
        r"https?://(www\.)?youtube\.com/playlist\?list=[\w-]+",
        r"https?://(www\.)?youtube\.com/watch\?v=[\w-]+(&list=[\w-]+)?",
        r"https?://youtu\.be/[\w-]+",
        r"https?://music\.youtube\.com/playlist\?list=[\w-]+",
        r"https?://music\.youtube\.com/watch\?v=[\w-]+(&list=[\w-]+)?",
    ]
    return any(re.match(p, text) for p in patterns)


def get_yt_dlp_cmd() -> list:
    """Return list of command parts to run yt-dlp: [exe] or [python, '-m', 'yt_dlp']."""
    exe = "yt-dlp"
    if sys.platform == "win32":
        exe = "yt-dlp.exe"
    for p in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(p, exe)
        if os.path.isfile(candidate):
            return [candidate]
    script_dir = Path(__file__).resolve().parent
    candidate = script_dir / exe
    if candidate.is_file():
        return [str(candidate)]
    try:
        import yt_dlp  # noqa: F401

        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        pass
    return [exe]


def get_js_runtime_args() -> list:
    """Return yt-dlp args for a JS runtime. Deno is default; if missing, use node or bun."""
    if shutil.which("deno"):
        return []
    if shutil.which("node"):
        return ["--js-runtimes", "node"]
    if shutil.which("bun"):
        return ["--js-runtimes", "bun"]
    return []


def bitrate_to_quality(bitrate_label: str) -> str:
    return QUALITY_MAP.get(bitrate_label.strip(), "320K")


def build_yt_dlp_command(url: str, output_dir: str, bitrate_label: str) -> list:
    """Full argv for yt-dlp: extract audio to MP3 with metadata and progress."""
    quality = bitrate_to_quality(bitrate_label)
    out_tmpl = os.path.join(
        output_dir, "%(playlist_index)02d - %(artist,Unknown)s - %(title)s.%(ext)s"
    )
    return (
        list(get_yt_dlp_cmd())
        + get_js_runtime_args()
        + [
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            quality,
            "-o",
            out_tmpl,
            "--embed-metadata",
            "--newline",
            "--progress",
            "--no-mtime",
            url,
        ]
    )


def parse_progress_line(line: str) -> Optional[float]:
    """Extract download percentage from a yt-dlp progress line. Returns 0–100 or None."""
    m = re.search(r"\[download\]\s*(\d+(?:\.\d+)?)\s*%", line)
    if m:
        return float(m.group(1))
    return None


@dataclass
class PlaylistTrackProgress:
    """Derived from yt-dlp stdout; do not count raw [download] 100%% lines (several per track)."""

    completed: int = 0
    total: Optional[int] = None

    def apply_line(self, line: str) -> None:
        """Update from one line of yt-dlp output."""
        # Starting track X of Y → X-1 tracks are fully done (yt-dlp prints this once per entry).
        m = re.search(
            r"(?:\[download\]\s*)?Downloading\s+item\s+(\d+)\s+of\s+(\d+)",
            line,
            re.I,
        )
        if m:
            current, tot = int(m.group(1)), int(m.group(2))
            self.total = tot
            self.completed = max(0, current - 1)
            return
        # Some extractors: "Downloading N items of M" (total playlist size; not per-track).
        m2 = re.search(r"Downloading\s+(\d+)\s+items?\s+of\s+(\d+)", line, re.I)
        if m2 and self.total is None:
            self.total = int(m2.group(2))

    def finalize_success(self) -> None:
        """When yt-dlp exits 0, last track is done even if no further 'item' line appears."""
        if self.total is not None:
            self.completed = self.total
