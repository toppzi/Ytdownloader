# YouTube Playlist → MP3

Simple GUI to download all tracks from a YouTube playlist (or a single video) as MP3 files.

**License:** [MIT](LICENSE) — use, modify, and distribute freely; keep the license notice.

## Requirements

- **Python 3.9+** with **tkinter** (often included; on Linux you may need `python3-tk`)
- **yt-dlp** – used to fetch and download from YouTube
- **ffmpeg** – used by yt-dlp to convert audio to MP3
- **A JavaScript runtime** (for YouTube) – the app auto-detects **Deno**, **Node** (20+), or **Bun**. Install one if you see a “No supported JavaScript runtime” warning: [yt-dlp EJS wiki](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

## Setup

```bash
cd yt-playlist-mp3
pip install -r requirements.txt
```

The `yt-dlp[default]` dependency includes the EJS scripts needed for YouTube. If you already had `yt-dlp` installed, run `pip install -U "yt-dlp[default]"` once to get them.

Install **ffmpeg** with your package manager if needed, for example:

- Fedora: `sudo dnf install ffmpeg`
- Ubuntu/Debian: `sudo apt install ffmpeg`
- Arch: `sudo pacman -S ffmpeg`

## Usage

```bash
python playlist_mp3_gui.py
```

1. Paste a YouTube **playlist** or **video** URL.
2. Click **Browse…** and choose the folder where MP3s should be saved.
3. Click **Download as MP3**.

Files are saved as `01 - Artist - Title.mp3`, `02 - Artist - Title.mp3`, … (with playlist order preserved).

## Notes

- Playlist URLs look like: `https://www.youtube.com/playlist?list=PL...`
- Single video URLs also work; one MP3 will be created.
- The **Stop** button cancels the current download.
- The last-used output folder is remembered (stored in `~/.config/yt-playlist-mp3/config.json`).

## Possible future improvements

- Progress bar (parse yt-dlp progress lines).
- Option to choose output filename pattern (e.g. with/without playlist index).
- “Open folder” button after download.
- Check for yt-dlp/ffmpeg/JS runtime at startup and show a clear message if something is missing.

## Legal disclaimer

This project is open-source software. **Uploading and sharing the code on GitHub is normal and legal** — many similar tools (e.g. yt-dlp, youtube-dl) are hosted there.

**Using** the tool may involve:

- **YouTube’s Terms of Service** — they generally disallow downloading except where they offer it. Violating ToS can lead to account action, not necessarily criminal liability.
- **Copyright** — most content on YouTube is copyrighted. Downloading it can be copyright infringement in some places unless an exception (e.g. fair use, your own uploads, content you have rights to) applies.

The software is provided as-is. Users are responsible for complying with applicable laws and with YouTube’s Terms of Service. This project does not encourage or endorse downloading content without proper rights or in breach of ToS.
