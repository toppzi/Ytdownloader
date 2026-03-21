(() => {
  const $ = (id) => document.getElementById(id);

  const urlEl = $("url");
  const outEl = $("output-dir");
  const bitrateEl = $("bitrate");
  const btnDl = $("btn-download");
  const btnStop = $("btn-stop");
  const btnClear = $("btn-clear-log");
  const logEl = $("log");
  const progressEl = $("progress");
  const statusEl = $("status");
  const tracksEl = $("tracks-status");

  let abortCtrl = null;

  function setTracks(completed, total) {
    if (total != null && total > 0) {
      tracksEl.textContent = completed + " of " + total + " track" + (total !== 1 ? "s" : "") + " downloaded";
    } else if (completed > 0) {
      tracksEl.textContent = completed + " track" + (completed !== 1 ? "s" : "") + " downloaded";
    } else {
      tracksEl.textContent = "";
    }
  }

  function setBusy(busy) {
    btnDl.disabled = busy;
    btnStop.disabled = !busy;
    urlEl.disabled = busy;
    outEl.disabled = busy;
    bitrateEl.disabled = busy;
  }

  function logLine(text) {
    logEl.textContent += text + "\n";
    logEl.scrollTop = logEl.scrollHeight;
  }

  function setStatus(msg, kind = "") {
    statusEl.textContent = msg;
    statusEl.className = "status " + kind;
  }

  function parseSSEChunk(buffer, onEvent) {
    const parts = buffer.split("\n\n");
    const rest = parts.pop() || "";
    for (const block of parts) {
      const line = block.trim();
      if (!line.startsWith("data: ")) continue;
      try {
        onEvent(JSON.parse(line.slice(6)));
      } catch (_) {
        /* ignore */
      }
    }
    return rest;
  }

  btnClear.addEventListener("click", () => {
    logEl.textContent = "";
  });

  btnStop.addEventListener("click", async () => {
    try {
      await fetch("/api/stop", { method: "POST" });
    } catch (_) {
      /* ignore */
    }
    if (abortCtrl) abortCtrl.abort();
    setBusy(false);
    setStatus("Stop requested.", "");
    logLine("[stopping…]");
  });

  btnDl.addEventListener("click", async () => {
    const url = urlEl.value.trim();
    const output_dir = outEl.value.trim();
    const bitrate = bitrateEl.value;

    logEl.textContent = "";
    progressEl.value = 0;
    progressEl.removeAttribute("value");
    setTracks(0, null);

    if (!url) {
      setStatus("Please enter a playlist or video URL.", "error");
      return;
    }
    if (!output_dir) {
      setStatus("Please enter a folder path where MP3s should be saved.", "error");
      return;
    }

    setBusy(true);
    setStatus("Connecting…", "");
    abortCtrl = new AbortController();

    try {
      const res = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, output_dir, bitrate }),
        signal: abortCtrl.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setStatus(err.detail || res.statusText || "Request failed", "error");
        setBusy(false);
        return;
      }

      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        buf = parseSSEChunk(buf, (ev) => {
          if (ev.type === "line" && ev.text) {
            logLine(ev.text);
          }
          if (ev.type === "tracks" && typeof ev.completed === "number") {
            setTracks(ev.completed, ev.total ?? null);
          }
          if (ev.type === "progress" && typeof ev.percent === "number") {
            progressEl.value = ev.percent;
          }
          if (ev.type === "done") {
            if (ev.code === 0) {
              progressEl.value = 100;
              setStatus("Download finished.", "ok");
            } else if (ev.code === 409) {
              setStatus("Another download was already running.", "error");
            } else {
              setStatus("Finished with errors (exit " + ev.code + ").", "error");
            }
          }
          if (ev.type === "error") {
            setStatus(ev.message || "Error", "error");
          }
        });
      }
    } catch (e) {
      if (e.name === "AbortError") {
        setStatus("Cancelled.", "");
      } else {
        setStatus(String(e.message || e), "error");
      }
    } finally {
      setBusy(false);
      abortCtrl = null;
    }
  });

  fetch("/api/config")
    .then((r) => r.json())
    .then((cfg) => {
      if (cfg.output_dir && !outEl.value) outEl.value = cfg.output_dir;
      if (cfg.bitrate_default) bitrateEl.value = cfg.bitrate_default;
    })
    .catch(() => {});

  urlEl.focus();
})();
