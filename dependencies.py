"""
Detect missing runtime dependencies and provide platform-specific install commands.
Used by the GUI (and optionally CLI). Does not import tkinter.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class DepIssue:
    """One missing or optional component."""

    id: str
    title: str
    detail: str
    is_blocking: bool
    # Shown in order for the detected platform, then fallbacks
    fix_commands: tuple[str, ...]


def detect_platform_family() -> str:
    """Rough OS family for install hints: fedora, debian, arch, macos, windows, unknown."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        try:
            txt = Path("/etc/os-release").read_text(encoding="utf-8").lower()
        except OSError:
            return "linux_unknown"
        if any(x in txt for x in ("fedora", "rhel", "centos", "rocky", "almalinux")):
            return "fedora"
        if any(x in txt for x in ("debian", "ubuntu", "linuxmint", "pop_os")):
            return "debian"
        if "arch" in txt or "manjaro" in txt:
            return "arch"
        return "linux_unknown"
    return "unknown"


def _yt_dlp_available() -> bool:
    from yt_playlist_core import get_yt_dlp_cmd

    cmd = get_yt_dlp_cmd()
    exe = cmd[0]
    if os.path.isfile(exe):
        return True
    if shutil.which("yt-dlp"):
        return True
    try:
        import yt_dlp  # noqa: F401

        return True
    except ImportError:
        return False


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _js_runtime_available() -> bool:
    return bool(shutil.which("deno") or shutil.which("node") or shutil.which("bun"))


def _pip_install_hint() -> str:
    """Command to install Python deps from project directory."""
    here = Path(__file__).resolve().parent
    req = here / "requirements.txt"
    if req.is_file():
        return f'cd "{here}" && python3 -m pip install -r requirements.txt'
    return "python3 -m pip install -r requirements.txt"


def collect_dependency_issues() -> list[DepIssue]:
    """
    Return missing components. yt-dlp and ffmpeg are treated as blocking for downloads.
    Missing JS runtime is a strong warning (YouTube needs EJS).
    """
    issues: list[DepIssue] = []

    if not _yt_dlp_available():
        issues.append(
            DepIssue(
                id="yt-dlp",
                title="yt-dlp",
                detail="Required to download from YouTube. Install the Python package from this project.",
                is_blocking=True,
                fix_commands=(_pip_install_hint(),),
            )
        )

    if not _ffmpeg_available():
        issues.append(
            DepIssue(
                id="ffmpeg",
                title="ffmpeg",
                detail="Required to convert audio to MP3.",
                is_blocking=True,
                fix_commands=_ffmpeg_commands_for_platform(),
            )
        )

    if not _js_runtime_available():
        issues.append(
            DepIssue(
                id="js-runtime",
                title="JavaScript runtime (Deno, Node, or Bun)",
                detail="YouTube extraction in yt-dlp needs a JS runtime. Install one of them.",
                is_blocking=False,
                fix_commands=_js_commands_for_platform(),
            )
        )

    return issues


def _ffmpeg_commands_for_platform() -> tuple[str, ...]:
    fam = detect_platform_family()
    if fam == "fedora":
        return ("sudo dnf install ffmpeg",)
    if fam == "debian":
        return ("sudo apt update && sudo apt install -y ffmpeg",)
    if fam == "arch":
        return ("sudo pacman -S ffmpeg",)
    if fam == "macos":
        return ("brew install ffmpeg",)
    if fam == "windows":
        return (
            "Install ffmpeg (e.g. winget install ffmpeg, or https://ffmpeg.org/download.html) "
            "and ensure it is on PATH.",
        )
    return (
        "Fedora: sudo dnf install ffmpeg",
        "Debian/Ubuntu: sudo apt install ffmpeg",
        "Arch: sudo pacman -S ffmpeg",
    )


def _js_commands_for_platform() -> tuple[str, ...]:
    fam = detect_platform_family()
    if fam == "fedora":
        return (
            "sudo dnf install nodejs   # or: curl -fsSL https://deno.land/install.sh | sh",
        )
    if fam == "debian":
        return ("sudo apt install -y nodejs", "  # or install Deno / Bun from their sites")
    if fam == "arch":
        return ("sudo pacman -S nodejs npm", "  # or: deno, or bun-bin from AUR")
    if fam == "macos":
        return ("brew install node", "  # or: brew install deno")
    if fam == "windows":
        return ("Install Node.js LTS from https://nodejs.org/ (or Deno / Bun).",)
    return (
        "Install Node 20+, Deno, or Bun and ensure it is on PATH.",
        "See: https://github.com/yt-dlp/yt-dlp/wiki/EJS",
    )


def format_issues_report(issues: list[DepIssue]) -> str:
    """Plain text for dialog / clipboard."""
    lines: list[str] = []
    for i in issues:
        lines.append(f"• {i.title}")
        lines.append(f"  {i.detail}")
        for cmd in i.fix_commands:
            lines.append(f"  → {cmd}")
        lines.append("")
    return "\n".join(lines).rstrip()


def try_clipboard_copy(text: str) -> bool:
    """Best-effort copy without tkinter (Linux: xclip/xsel/wl-copy)."""
    if sys.platform == "darwin":
        try:
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=5)
            return True
        except (OSError, subprocess.SubprocessError):
            return False
    if sys.platform == "win32":
        try:
            subprocess.run(["clip"], input=text, text=True, check=True, timeout=5)
            return True
        except (OSError, subprocess.SubprocessError):
            return False
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
        try:
            subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=5)
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False
