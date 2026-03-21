# YouTube Playlist → MP3

Download a **YouTube** or **YouTube Music** playlist (or a single video) as **MP3** files on your own computer, using [yt-dlp](https://github.com/yt-dlp/yt-dlp).

**Three ways to use it:**

| Mode | Command | Notes |
|------|---------|--------|
| **Desktop GUI** | `python playlist_mp3_gui.py` | tkinter; browse for folder |
| **Terminal** | `python playlist_mp3_cli.py` | Rich wizard or flags |
| **Web (localhost)** | `python web_app.py` | Browser UI; no tkinter |

**License:** [MIT](LICENSE) — use, modify, and distribute freely; keep the license notice.

## Project layout

| File / folder | Purpose |
|---------------|---------|
| `yt_playlist_core.py` | Shared: URL checks, yt-dlp command, config, playlist progress parsing |
| `dependencies.py` | Detect missing ffmpeg / yt-dlp / JS runtime; install hints |
| `playlist_mp3_gui.py` | Desktop GUI |
| `playlist_mp3_cli.py` | Rich CLI |
| `web_app.py` | FastAPI + SSE for the browser UI |
| `static/` | `index.html`, `styles.css`, `app.js` for the web UI |
| `requirements.txt` | Python dependencies |

## Features

- **Progress:** per-file percentage bar plus **playlist position** (e.g. *35 of 71 tracks downloaded*), derived from yt-dlp’s `Downloading item X of Y` lines (not raw `100%` spam).
- **Output folder:** if the path does not exist, **parent folders are created** automatically (unless the path is an existing file).
- **GUI:** **Help → Setup & dependencies** and a startup check list missing tools with copy-paste install commands.
- **Web:** binds to **127.0.0.1** by default; see security note below.

## Requirements

- **Python 3.9+** with **tkinter** (often included; on Linux you may need a separate package — see below)
- **yt-dlp** – used to fetch and download from YouTube
- **ffmpeg** – used by yt-dlp to convert audio to MP3
- **A JavaScript runtime** (for YouTube) – the app auto-detects **Deno**, **Node** (20+), or **Bun**. Install one if you see a “No supported JavaScript runtime” warning: [yt-dlp EJS wiki](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

## Before you run the GUI

Do these in order:

| Step | What | Why |
|------|------|-----|
| 1 | **Python 3.9+** from [python.org](https://www.python.org/) or your distro | Runs the app |
| 2 | **tkinter** (GUI toolkit) | Required only for `playlist_mp3_gui.py` |
| 3 | **Python deps** — `pip install -r requirements.txt` in this folder | Installs **yt-dlp**, **Rich** (CLI), **FastAPI** + **Uvicorn** (web UI) |
| 4 | **ffmpeg** | Converts audio to MP3 |
| 5 | **Node, Deno, or Bun** | YouTube extraction in yt-dlp needs a JS runtime |

**tkinter on Linux** (pick one for your distro):

| Distro | Command |
|--------|---------|
| Fedora / RHEL-style | `sudo dnf install python3-tkinter` |
| Debian / Ubuntu | `sudo apt install python3-tk` |
| Arch | `sudo pacman -S tk` |

Windows and macOS builds from **python.org** usually include tkinter already.

**After installing anything**, run `python playlist_mp3_gui.py` again.

### Help inside the app

When something is missing, the GUI opens a **Setup** window with copy-paste commands. You can always open it from **Help → Setup & dependencies…**.

## Setup

```bash
cd Ytdownloader   # or your clone folder name
pip install -r requirements.txt
```

Or explicitly:

```bash
python3 -m pip install -r requirements.txt
```

The `yt-dlp[default]` dependency includes the EJS scripts needed for YouTube. If you already had `yt-dlp` installed, run `pip install -U "yt-dlp[default]"` once to get them.

Install **ffmpeg** with your package manager if needed, for example:

- Fedora: `sudo dnf install ffmpeg`
- Ubuntu/Debian: `sudo apt install ffmpeg`
- Arch: `sudo pacman -S ffmpeg`

## Usage

### GUI

```bash
python playlist_mp3_gui.py
```

1. Paste a YouTube **playlist** or **video** URL.
2. Click **Browse…** and choose the folder where MP3s should be saved (or type a path — missing folders are created).
3. Click **Download as MP3**.

While a playlist runs, the bar shows file progress and a line like **“X of Y tracks downloaded”** when yt-dlp reports playlist position.

### Web UI (browser)

Runs a **small server on your computer only** (not in the cloud). The page in your browser talks to **localhost**; **yt-dlp** still runs on your machine with the same rules as the GUI. **You do not need tkinter** for this mode.

```bash
python web_app.py
```

Then open **http://127.0.0.1:8742** in your browser (or the URL printed in the terminal).

- Paste a **URL**, type an **absolute folder path** where MP3s should go (browsers cannot pick folders for you), choose **bitrate**, then **Download**.
- **Stop** sends cancel to the running job.
- **Security:** the server defaults to **127.0.0.1** (only this PC). Do not change `YTMP3_HOST` to `0.0.0.0` on untrusted networks — there is no login; anyone who can reach the port could trigger downloads.

Optional environment variables:

| Variable | Default | Meaning |
|----------|---------|---------|
| `YTMP3_HOST` | `127.0.0.1` | Bind address |
| `YTMP3_PORT` | `8742` | Port |

### Terminal (Rich UI)

```bash
python playlist_mp3_cli.py
```

With **no arguments**, the screen clears and a **step-by-step wizard** opens: centered welcome panel, then **Step 1** (paste URL, with validation), **Step 2** (save folder), **Step 3** (pick MP3 quality from a numbered table), a **review** panel, and confirmation. Then a **progress bar** and status line while `yt-dlp` runs.

- `-y` — skip the final “Start download?” prompt  
- `--no-clear` — keep existing terminal output (don’t clear before the wizard)

**Examples**

```bash
# Non-interactive: URL + output folder (folder defaults to last-used from config or current directory if omitted)
python playlist_mp3_cli.py "https://www.youtube.com/playlist?list=PL…" -o ~/Music/youtube

# Bitrate: 128, 192, 256, 320, or best (VBR)
python playlist_mp3_cli.py "https://youtu.be/…" -o ./out -b best

# Full yt-dlp log (verbose)
python playlist_mp3_cli.py "URL" -o ./out -v
```

Files are saved as `01 - Artist - Title.mp3`, `02 - Artist - Title.mp3`, … (with playlist order preserved).

## Notes

- Playlist URLs look like: `https://www.youtube.com/playlist?list=PL...`
- Single video URLs also work; one MP3 will be created.
- **Stop** (GUI / web) or **Ctrl+C** in the terminal cancels the current run.
- The last-used output folder is remembered (stored in `~/.config/yt-playlist-mp3/config.json`).
- If the output path does not exist yet, the app **creates the folder and any missing parents** (e.g. `…/Music/JazzyBeats`). If the path already exists as a **file**, you get an error instead.
- **Playlist counts** depend on yt-dlp’s log format; on a successful exit, the UI sets “all tracks done” even if the last line was mid-playlist.

## Possible future improvements

- Option to choose output filename pattern (e.g. with/without playlist index).
- “Open folder” button after download.

## Legal disclaimer

This project is open-source software. **Uploading and sharing the code on GitHub is normal and legal** — many similar tools (e.g. yt-dlp, youtube-dl) are hosted there.

**Using** the tool may involve:

- **YouTube’s Terms of Service** — they generally disallow downloading except where they offer it. Violating ToS can lead to account action, not necessarily criminal liability.
- **Copyright** — most content on YouTube is copyrighted. Downloading it can be copyright infringement in some places unless an exception (e.g. fair use, your own uploads, content you have rights to) applies.

The software is provided as-is. Users are responsible for complying with applicable laws and with YouTube’s Terms of Service. This project does not encourage or endorse downloading content without proper rights or in breach of ToS.
