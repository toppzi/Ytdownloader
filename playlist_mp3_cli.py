#!/usr/bin/env python3
"""
YouTube Playlist → MP3 — terminal UI (Rich). Same behavior as the GUI.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import Optional

from yt_playlist_core import (
    BITRATE_LABELS,
    PlaylistTrackProgress,
    build_yt_dlp_command,
    ensure_output_dir,
    is_youtube_url,
    load_config,
    parse_progress_line,
    save_config,
)

try:
    from rich import box
    from rich.align import Align
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.prompt import Confirm, IntPrompt, Prompt
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("Install dependencies: pip install -r requirements.txt", file=sys.stderr)
    raise SystemExit(1)


APP_TITLE = "Playlist → MP3"
BITRATE_HINTS = (
    "Smaller files",
    "Good balance",
    "High quality",
    "Best CBR (default)",
    "Best variable bitrate",
)


def _parse_bitrate_arg(s: str) -> str:
    s = s.strip().lower().replace("_", " ")
    aliases = {
        "128": "128 kbps",
        "192": "192 kbps",
        "256": "256 kbps",
        "320": "320 kbps",
        "best": "Best (VBR)",
        "vbr": "Best (VBR)",
        "0": "Best (VBR)",
    }
    if s in aliases:
        return aliases[s]
    for label in BITRATE_LABELS:
        if label.lower() == s:
            return label
    raise argparse.ArgumentTypeError(
        f"invalid bitrate {s!r}; use one of: 128, 192, 256, 320, best, or full label like '320 kbps'"
    )


def _validate_and_resolve(
    url: Optional[str],
    output_dir: Optional[str],
    bitrate: str,
    console: Console,
) -> tuple[str, str, str] | None:
    url = (url or "").strip()
    if not url:
        console.print("[red]URL is required.[/red] Pass it as an argument or run without args for the wizard.")
        return None
    if not is_youtube_url(url):
        console.print("[red]That does not look like a valid YouTube or YouTube Music URL.[/red]")
        return None
    out = (output_dir or "").strip()
    if not out:
        console.print("[red]Output directory is required.[/red] Use -o/--output or run interactively.")
        return None
    try:
        out = ensure_output_dir(out)
    except NotADirectoryError as e:
        console.print(f"[red]{e}[/red]")
        return None
    except OSError as e:
        console.print(f"[red]Could not create folder:[/red] {e}")
        return None
    return url, out, bitrate


def _render_welcome(console: Console) -> None:
    """Full-screen style welcome: title, tagline, what you need."""
    header = Text()
    header.append(APP_TITLE + "\n", style="bold bright_white")
    header.append(
        "YouTube & YouTube Music  ·  MP3 with metadata  ·  yt-dlp + ffmpeg",
        style="dim",
    )
    tips = Table.grid(padding=(0, 2))
    tips.add_column(style="cyan", justify="right")
    tips.add_column(style="dim")
    tips.add_row("Files saved as", "01 - Artist - Title.mp3, 02 - …")
    tips.add_row("Requires", "yt-dlp, ffmpeg, and a JS runtime (Deno / Node / Bun)")

    body = Group(
        Align.center(header),
        Text(""),
        Align.center(tips),
    )
    console.print()
    console.print(
        Panel.fit(
            body,
            box=box.DOUBLE_EDGE,
            border_style="bright_blue",
            padding=(1, 3),
        ),
        justify="center",
    )
    console.print(
        Align.center(Text("Follow the steps below. Press Ctrl+C to cancel.", style="dim italic")),
    )
    console.print()


def _prompt_url(console: Console) -> str:
    console.print(Rule("[bold cyan]Step 1[/bold cyan]  Paste your link", style="dim"))
    console.print(
        "  [dim]Playlist:[/dim]  [link]https://www.youtube.com/playlist?list=…[/link]\n"
        "  [dim]Video:[/dim]     [link]https://youtu.be/…[/link]  or  music.youtube.com",
        highlight=False,
    )
    console.print()
    while True:
        url = Prompt.ask("  [bold]URL[/bold]", default="").strip()
        if not url:
            console.print("  [yellow]Please paste a URL (cannot be empty).[/yellow]")
            continue
        if not is_youtube_url(url):
            console.print(
                "  [red]That does not look like a YouTube or YouTube Music URL.[/red] "
                "[dim]Try again.[/dim]"
            )
            continue
        return url


def _prompt_output_dir(console: Console, default_out: str) -> str:
    console.print()
    console.print(Rule("[bold cyan]Step 2[/bold cyan]  Where to save MP3s", style="dim"))
    console.print(f"  [dim]Default is your last folder or current directory.[/dim]\n")
    while True:
        raw = Prompt.ask("  [bold]Folder path[/bold]", default=default_out).strip()
        try:
            return ensure_output_dir(raw)
        except NotADirectoryError as e:
            console.print(f"  [red]{e}[/red]\n  [dim]Choose a path that is not an existing file.[/dim]")
        except OSError as e:
            console.print(f"  [red]Could not create folder:[/red] {e}")


def _prompt_bitrate(console: Console) -> str:
    console.print()
    console.print(Rule("[bold cyan]Step 3[/bold cyan]  MP3 quality", style="dim"))
    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold",
        border_style="dim",
        padding=(0, 1),
    )
    table.add_column("#", justify="right", style="cyan", width=3)
    table.add_column("Bitrate", style="white")
    table.add_column("", style="dim")
    for i, (label, hint) in enumerate(zip(BITRATE_LABELS, BITRATE_HINTS), start=1):
        table.add_row(str(i), label, hint)
    console.print(table)
    console.print()
    default_n = 4  # 320 kbps
    while True:
        n = IntPrompt.ask(
            "  [bold]Choice[/bold] [dim](1–5)[/dim]",
            default=default_n,
        )
        if 1 <= n <= len(BITRATE_LABELS):
            return BITRATE_LABELS[n - 1]
        console.print(f"  [yellow]Pick a number between 1 and {len(BITRATE_LABELS)}.[/yellow]")


def interactive_wizard(console: Console, no_clear: bool) -> tuple[str, str, str]:
    if not no_clear:
        console.clear()
    cfg = load_config()
    default_out = cfg.get("output_dir") or os.getcwd()

    _render_welcome(console)
    url = _prompt_url(console)
    out = _prompt_output_dir(console, default_out)
    bitrate = _prompt_bitrate(console)

    console.print()
    console.print(Rule(style="dim"))
    review = Table(show_header=False, box=None, padding=(0, 1))
    review.add_column(style="dim", justify="right", width=10)
    review.add_column()
    review.add_row("URL", Text(url, overflow="fold"))
    review.add_row("Save to", out)
    review.add_row("Quality", bitrate)
    console.print(
        Panel(
            review,
            title="[bold green]Ready to download[/bold green]",
            border_style="green",
            box=box.ROUNDED,
        )
    )
    console.print()
    return url, out, bitrate


def run_download(
    url: str,
    output_dir: str,
    bitrate_label: str,
    console: Console,
    verbose: bool = False,
    *,
    show_ready_panel: bool = True,
) -> int:
    cmd = build_yt_dlp_command(url, output_dir, bitrate_label)
    save_config(load_config() | {"output_dir": output_dir})

    if show_ready_panel:
        console.print()
        summary = Table(show_header=False, box=None, padding=(0, 2))
        summary.add_column(style="dim", justify="right")
        summary.add_column()
        summary.add_row("URL", Text(url, overflow="fold"))
        summary.add_row("Output", output_dir)
        summary.add_row("Bitrate", bitrate_label)
        console.print(
            Panel(summary, title="[bold]Starting[/bold]", border_style="blue", box=box.ROUNDED)
        )
        console.print()

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        console.print(
            "[red]yt-dlp not found.[/red] Install: [bold]pip install -r requirements.txt[/bold]\n"
            "Also install [bold]ffmpeg[/bold] (e.g. [dim]sudo dnf install ffmpeg[/dim])."
        )
        return 127

    assert proc.stdout is not None
    returncode = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task("yt-dlp", total=100.0)
        progress.update(task_id, completed=0, description="Connecting…")
        pt = PlaylistTrackProgress()

        def _desc() -> str:
            if pt.total is not None and pt.total > 0:
                return f"{pt.completed} of {pt.total} tracks"
            return ""

        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            if verbose:
                console.print(line, style="dim", highlight=False)
            pt.apply_line(line)
            pct = parse_progress_line(line)
            if pct is not None:
                desc = _desc() or line[: min(70, len(line))]
                progress.update(task_id, completed=pct, description=desc)
            else:
                desc = _desc() or (line[:85] + "…" if len(line) > 85 else line[:85])
                if not verbose:
                    progress.update(task_id, description=desc)

        returncode = proc.wait()
        if returncode == 0:
            pt.finalize_success()
            progress.update(task_id, description=_desc() or "Done")

    if returncode == 0:
        console.print()
        console.print(
            Panel(
                "[bold green]All done.[/bold green]  Your MP3s are in the folder you chose.",
                border_style="green",
                box=box.ROUNDED,
            )
        )
    else:
        console.print()
        console.print(f"[bold red]Finished with exit code {returncode}.[/bold red]")
    return returncode


def main(argv: Optional[list[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    console = Console(highlight=False, soft_wrap=True)

    p = argparse.ArgumentParser(
        description="Download a YouTube / YouTube Music playlist or video as MP3 (terminal UI).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("url", nargs="?", help="Playlist or video URL")
    p.add_argument(
        "-o",
        "--output",
        dest="output_dir",
        metavar="DIR",
        help="Folder to save MP3 files",
    )
    p.add_argument(
        "-b",
        "--bitrate",
        default="320 kbps",
        type=str,
        help="128, 192, 256, 320, or best (VBR); or e.g. '320 kbps'",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print every yt-dlp line (noisy)",
    )
    p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation before download",
    )
    p.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear the screen before the interactive wizard",
    )
    args = p.parse_args(argv)

    try:
        bitrate = _parse_bitrate_arg(args.bitrate)
    except argparse.ArgumentTypeError as e:
        console.print(f"[red]{e}[/red]")
        return 2

    if not args.url:
        url, out, bitrate = interactive_wizard(console, no_clear=args.no_clear)
    else:
        url = args.url.strip()
        raw_out = args.output_dir
        if not raw_out:
            raw_out = load_config().get("output_dir") or os.getcwd()
        out = os.path.abspath(os.path.expanduser(raw_out.strip()))

    resolved = _validate_and_resolve(url, out, bitrate, console)
    if not resolved:
        return 2
    url, out, bitrate = resolved

    if not args.yes:
        if not Confirm.ask("[bold]Start download now?[/bold]", default=True):
            console.print("[dim]Cancelled.[/dim]")
            return 0

    # Wizard already showed a review panel; skip duplicate "Starting" panel
    show_panel = bool(args.url)
    return run_download(url, out, bitrate, console, verbose=args.verbose, show_ready_panel=show_panel)


if __name__ == "__main__":
    raise SystemExit(main())
