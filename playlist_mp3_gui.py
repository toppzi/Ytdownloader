#!/usr/bin/env python3
"""YouTube Playlist to MP3 Downloader — GUI using yt-dlp."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import Optional

try:
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import ttk, filedialog, messagebox, scrolledtext
except ImportError:
    tk = None  # type: ignore[misc, assignment]
    tkfont = None  # type: ignore[misc, assignment]
    ttk = None  # type: ignore[misc, assignment]
    filedialog = None  # type: ignore[misc, assignment]
    messagebox = None  # type: ignore[misc, assignment]
    scrolledtext = None  # type: ignore[misc, assignment]

from dependencies import DepIssue, collect_dependency_issues, format_issues_report
from yt_playlist_core import (
    PlaylistTrackProgress,
    build_yt_dlp_command,
    ensure_output_dir,
    is_youtube_url,
    load_config,
    parse_progress_line,
    save_config,
)


# Placeholder shown in URL entry until user focuses
PLACEHOLDER_URL = "https://music.youtube.com/playlist?list=..."

# UI palette (light theme, high contrast log)
_COL = {
    "bg": "#f1f5f9",
    "header": "#0f172a",
    "header_sub": "#94a3b8",
    "card": "#ffffff",
    "border": "#e2e8f0",
    "text": "#0f172a",
    "muted": "#64748b",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "log_bg": "#0c0c0f",
    "log_fg": "#e4e4e7",
    "log_sel": "#3b82f6",
}


def _default_font_family() -> str:
    try:
        return tkfont.nametofont("TkDefaultFont").actual()["family"]
    except tk.TclError:
        return "TkDefaultFont"


def _print_tkinter_install_help() -> None:
    from dependencies import detect_platform_family

    fam = detect_platform_family()
    print("tkinter is not installed — the GUI cannot start.", file=sys.stderr)
    print(file=sys.stderr)
    if fam == "fedora":
        print("  Fedora:  sudo dnf install python3-tkinter", file=sys.stderr)
    elif fam == "debian":
        print("  Debian/Ubuntu:  sudo apt install python3-tk", file=sys.stderr)
    elif fam == "arch":
        print("  Arch:  sudo pacman -S tk", file=sys.stderr)
    else:
        print("  Linux: install the tk package for your distro (often python3-tk or python3-tkinter).", file=sys.stderr)
    print("  Windows/macOS: use the official Python installer from python.org (includes tkinter).", file=sys.stderr)


class PlaylistMP3App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("YouTube Playlist → MP3")
        self.root.minsize(560, 480)
        self.root.geometry("680x560")
        self.root.configure(bg=_COL["bg"])

        self.download_running = False
        self.process = None
        self._playlist_track_progress: Optional[PlaylistTrackProgress] = None
        self._ff = _default_font_family()

        self._apply_style()
        self._build_ui()

    def _apply_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        bg, card, border = _COL["bg"], _COL["card"], _COL["border"]
        text, muted, accent = _COL["text"], _COL["muted"], _COL["accent"]

        style.configure(".", background=bg, foreground=text)
        style.configure("TFrame", background=bg)
        style.configure("Inner.TFrame", background=card)
        style.configure("Card.TFrame", background=card, relief="flat")
        style.configure("TLabel", background=bg, foreground=text, font=(self._ff, 10))
        style.configure("Muted.TLabel", background=bg, foreground=muted, font=(self._ff, 9))
        style.configure("Card.TLabel", background=card, foreground=text, font=(self._ff, 10))
        style.configure("CardMuted.TLabel", background=card, foreground=muted, font=(self._ff, 9))
        style.configure("TLabelFrame", background=card, foreground=text, relief="solid", borderwidth=1)
        style.configure("TLabelFrame.Label", background=card, foreground=muted, font=(self._ff, 9, "bold"))
        style.configure(
            "TEntry",
            fieldbackground=card,
            foreground=text,
            insertcolor=text,
            padding=6,
        )
        style.configure(
            "TCombobox",
            fieldbackground=card,
            background=card,
            foreground=text,
            arrowcolor=text,
            padding=4,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", card)],
            selectbackground=[("readonly", accent)],
            selectforeground=[("readonly", "#ffffff")],
        )
        style.configure(
            "TProgressbar",
            background=accent,
            troughcolor=border,
            borderwidth=0,
            thickness=10,
        )
        style.configure("TButton", font=(self._ff, 10), padding=(14, 8))
        style.configure("Accent.TButton", font=(self._ff, 10, "bold"))
        style.map(
            "Accent.TButton",
            background=[("active", _COL["accent_hover"]), ("pressed", _COL["accent_hover"])],
            foreground=[("disabled", "#94a3b8")],
        )
        style.configure(
            "Accent.TButton",
            background=accent,
            foreground="#ffffff",
            padding=(18, 10),
        )
        style.configure("Ghost.TButton", background=card, foreground=text)
        style.map("Ghost.TButton", background=[("active", border)])

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=0)
        outer.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(outer, bg=_COL["header"], padx=24, pady=20)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="Playlist → MP3",
            font=(self._ff, 20, "bold"),
            fg="#f8fafc",
            bg=_COL["header"],
        ).pack(anchor=tk.W)
        tk.Label(
            header,
            text="YouTube & YouTube Music · extract audio with yt-dlp",
            font=(self._ff, 11),
            fg=_COL["header_sub"],
            bg=_COL["header"],
        ).pack(anchor=tk.W, pady=(4, 0))

        main = ttk.Frame(outer, padding=(20, 16))
        main.pack(fill=tk.BOTH, expand=True)

        url_card = ttk.LabelFrame(main, text="SOURCE", padding=(14, 12))
        url_card.pack(fill=tk.X, pady=(0, 12))
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(url_card, textvariable=self.url_var, width=70)
        url_entry.pack(fill=tk.X, pady=(4, 0))
        url_entry.delete(0, tk.END)
        url_entry.insert(0, PLACEHOLDER_URL)
        url_entry.bind("<FocusIn>", lambda e: self._clear_placeholder(url_entry))

        out_card = ttk.LabelFrame(main, text="OUTPUT", padding=(14, 12))
        out_card.pack(fill=tk.X, pady=(0, 12))
        row = ttk.Frame(out_card, style="Inner.TFrame")
        row.pack(fill=tk.X)
        self.path_var = tk.StringVar(value=load_config().get("output_dir", ""))
        path_entry = ttk.Entry(row, textvariable=self.path_var, width=50)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(row, text="Browse…", style="Ghost.TButton", command=self._browse).pack(side=tk.LEFT)

        opts = ttk.Frame(main)
        opts.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(opts, text="MP3 bitrate", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 10))
        self.bitrate_var = tk.StringVar(value="320 kbps")
        bitrate_combo = ttk.Combobox(
            opts,
            textvariable=self.bitrate_var,
            values=["128 kbps", "192 kbps", "256 kbps", "320 kbps", "Best (VBR)"],
            state="readonly",
            width=16,
        )
        bitrate_combo.pack(side=tk.LEFT)

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_label = ttk.Label(main, text="", style="Muted.TLabel")
        self.progress_label.pack(anchor=tk.W, pady=(0, 2))
        self.progress_bar = ttk.Progressbar(
            main, variable=self.progress_var, maximum=100.0, mode="determinate"
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 12))

        btn_row = ttk.Frame(main)
        btn_row.pack(fill=tk.X, pady=(0, 10))
        self.btn_download = ttk.Button(
            btn_row, text="Download as MP3", style="Accent.TButton", command=self._start_download
        )
        self.btn_download.pack(side=tk.LEFT, padx=(0, 10))
        self.btn_stop = ttk.Button(
            btn_row, text="Stop", style="Ghost.TButton", command=self._stop_download, state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT)

        log_wrap = ttk.Frame(main)
        log_wrap.pack(fill=tk.BOTH, expand=True)
        log_hdr = ttk.Frame(log_wrap)
        log_hdr.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(log_hdr, text="Activity log", style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Button(log_hdr, text="Clear", style="Ghost.TButton", command=self._clear_log).pack(side=tk.RIGHT)

        log_frame = tk.Frame(log_wrap, bg=_COL["border"], padx=1, pady=1)
        log_frame.pack(fill=tk.BOTH, expand=True)
        mono = tkfont.Font(family="TkFixedFont", size=10)
        self.log = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=mono,
            bg=_COL["log_bg"],
            fg=_COL["log_fg"],
            insertbackground=_COL["log_fg"],
            selectbackground=_COL["log_sel"],
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=12,
            pady=10,
        )
        self.log.pack(fill=tk.BOTH, expand=True)

        self._log("Paste a YouTube or YouTube Music playlist/video URL, choose a folder, then click Download as MP3.")
        self._log("Requires: yt-dlp and ffmpeg on PATH (or in this folder).")
        self._log("")

        self._build_menubar()
        self.root.after(150, self._show_startup_dependency_help)

    def _build_menubar(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Setup & dependencies…", command=self._open_setup_help)

    def _open_setup_help(self) -> None:
        issues = collect_dependency_issues()
        if not issues:
            messagebox.showinfo(
                "Setup & dependencies",
                "Everything this app looks for is installed.\n\n"
                "• yt-dlp (Python package)\n"
                "• ffmpeg\n"
                "• A JS runtime (Deno / Node / Bun) for YouTube\n\n"
                "If downloads still fail, check the log and see README.md.",
            )
        else:
            self._show_dependency_dialog(issues)

    def _show_dependency_dialog(self, issues: list[DepIssue]) -> None:
        win = tk.Toplevel(self.root)
        win.title("Setup — install missing tools")
        win.geometry("660x440")
        win.minsize(500, 320)
        win.transient(self.root)
        outer = ttk.Frame(win, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            outer,
            text="Install the items below, then try again. Use Copy to paste commands into a terminal.",
            wraplength=620,
        ).pack(anchor=tk.W, pady=(0, 8))
        body = ttk.Frame(outer)
        body.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        text = format_issues_report(issues)
        st = scrolledtext.ScrolledText(
            body,
            height=16,
            wrap=tk.WORD,
            font=("TkFixedFont", 10),
            state=tk.NORMAL,
        )
        st.pack(fill=tk.BOTH, expand=True)
        st.insert("1.0", text)
        st.configure(state=tk.DISABLED)

        def copy_all() -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()

        btn_row = ttk.Frame(outer)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="Copy to clipboard", command=copy_all).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Close", style="Ghost.TButton", command=win.destroy).pack(side=tk.RIGHT)

    def _show_startup_dependency_help(self) -> None:
        issues = collect_dependency_issues()
        if issues:
            self._show_dependency_dialog(issues)

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
        self.progress_label.configure(text="")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start(8)

    def _progress_set_tracks(self, completed: int, total: Optional[int]):
        """Update 'X of Y songs' label."""
        if total is not None and total > 0:
            label = f"{completed} of {total} track{'s' if total != 1 else ''} downloaded"
        elif completed > 0:
            label = f"{completed} track{'s' if completed != 1 else ''} downloaded"
        else:
            label = ""
        self.progress_label.configure(text=label)

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
        try:
            out = ensure_output_dir(out)
        except NotADirectoryError as e:
            messagebox.showerror("Invalid path", str(e))
            return
        except OSError as e:
            messagebox.showerror("Could not create folder", str(e))
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
        cmd = build_yt_dlp_command(url, output_dir, bitrate)
        self._playlist_track_progress = PlaylistTrackProgress()
        pt = self._playlist_track_progress
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
                    pt.apply_line(line)
                    self.root.after(
                        0,
                        lambda: self._progress_set_tracks(pt.completed, pt.total),
                    )
                    percent = parse_progress_line(line)
                    if percent is not None:
                        self.root.after(0, lambda p=percent: self._progress_set_percent(p))
            returncode = self.process.wait()
            if returncode == 0:
                pt.finalize_success()
                self.root.after(0, lambda: self._progress_set_tracks(pt.completed, pt.total))
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


def main() -> None:
    if tk is None:
        _print_tkinter_install_help()
        raise SystemExit(1)
    app = PlaylistMP3App()
    app.run()


if __name__ == "__main__":
    main()
