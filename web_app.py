#!/usr/bin/env python3
"""
Local web UI for Playlist → MP3. Serves a browser UI on localhost only; yt-dlp runs on your machine.

Run: python web_app.py
Then open http://127.0.0.1:8742 in your browser.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Generator, Optional

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
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field
except ImportError as e:
    raise SystemExit(
        "Install web dependencies: python3 -m pip install fastapi uvicorn[standard]\n"
        "Or: pip install -r requirements.txt"
    ) from e


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

_dl_lock = threading.Lock()
_download_sem = threading.Semaphore(1)
_active_proc: Optional[subprocess.Popen] = None


class DownloadBody(BaseModel):
    url: str = Field(..., min_length=1)
    output_dir: str = Field(..., min_length=1)
    bitrate: str = Field(default="320 kbps")


app = FastAPI(title="Playlist → MP3", version="1.0.0")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.get("/api/config")
def api_config() -> dict[str, str]:
    cfg = load_config()
    out = cfg.get("output_dir", "")
    return {
        "output_dir": out if isinstance(out, str) else "",
        "bitrate_default": "320 kbps",
    }


@app.post("/api/stop")
def api_stop() -> dict[str, str]:
    with _dl_lock:
        proc = _active_proc
    if proc is not None and proc.poll() is None:
        proc.terminate()
        return {"status": "terminating"}
    return {"status": "idle"}


def _download_stream(body: DownloadBody) -> Generator[str, None, None]:
    global _active_proc

    if not _download_sem.acquire(blocking=False):
        yield _sse({"type": "error", "message": "Another download is already running."})
        yield _sse({"type": "done", "code": 409})
        return

    proc: Optional[subprocess.Popen] = None
    try:
        url = body.url.strip()
        if not is_youtube_url(url):
            yield _sse({"type": "error", "message": "Not a valid YouTube or YouTube Music URL."})
            yield _sse({"type": "done", "code": 2})
            return

        try:
            out_dir = ensure_output_dir(body.output_dir)
        except NotADirectoryError as e:
            yield _sse({"type": "error", "message": str(e)})
            yield _sse({"type": "done", "code": 2})
            return
        except OSError as e:
            yield _sse({"type": "error", "message": f"Could not create folder: {e}"})
            yield _sse({"type": "done", "code": 2})
            return

        br = body.bitrate.strip()
        if br not in BITRATE_LABELS:
            yield _sse(
                {"type": "error", "message": f"Invalid bitrate. Use one of: {', '.join(BITRATE_LABELS)}"}
            )
            yield _sse({"type": "done", "code": 2})
            return

        save_config(load_config() | {"output_dir": out_dir})
        cmd = build_yt_dlp_command(url, out_dir, br)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            yield _sse(
                {
                    "type": "error",
                    "message": "yt-dlp not found. Install: pip install -r requirements.txt",
                }
            )
            yield _sse({"type": "done", "code": 127})
            return

        with _dl_lock:
            _active_proc = proc

        returncode = 0
        pt = PlaylistTrackProgress()
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    yield _sse({"type": "line", "text": line})
                    pt.apply_line(line)
                    yield _sse(
                        {
                            "type": "tracks",
                            "completed": pt.completed,
                            "total": pt.total,
                        }
                    )
                    pct = parse_progress_line(line)
                    if pct is not None:
                        yield _sse({"type": "progress", "percent": pct})
            returncode = proc.wait()
            if returncode == 0:
                pt.finalize_success()
                yield _sse(
                    {"type": "tracks", "completed": pt.completed, "total": pt.total}
                )
        except Exception as e:
            returncode = -1
            yield _sse({"type": "line", "text": f"Error: {e}"})
        finally:
            with _dl_lock:
                if _active_proc is proc:
                    _active_proc = None

        yield _sse({"type": "done", "code": returncode})
    finally:
        _download_sem.release()


@app.post("/api/download")
def api_download(body: DownloadBody) -> StreamingResponse:
    return StreamingResponse(
        _download_stream(body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


def main() -> None:
    import uvicorn

    host = os.environ.get("YTMP3_HOST", "127.0.0.1")
    port = int(os.environ.get("YTMP3_PORT", "8742"))
    print(f"\n  Playlist → MP3  →  http://{host}:{port}\n  Press Ctrl+C to stop.\n")
    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
