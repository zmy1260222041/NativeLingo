import { clientLog } from "./runtime.js";

export function pickMime() {
  const candidates = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", ""];
  for (const candidate of candidates) {
    if (!candidate || (window.MediaRecorder && MediaRecorder.isTypeSupported(candidate))) {
      return candidate;
    }
  }
  return "";
}

export function createRecorder() {
  return {
    mediaRecorder: null,
    chunks: [],
    recording: false,
    prepared: false,
    blob: null,
    stream: null,
    _onStop: null,
    _finalized: false,
    _finalize() {
      if (this._finalized) return;
      this._finalized = true;
      const type = this.mediaRecorder?.mimeType || "audio/mp4";
      this.blob = new Blob(this.chunks, { type });
      clientLog(`recorder finalize; chunks=${this.chunks.length} blob=${this.blob.size}`);
      this.stream?.getTracks().forEach((track) => track.stop());
      this._onStop?.(this.blob);
    },
    async prepare(onStop) {
      this._onStop = onStop;
      this._finalized = false;
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.chunks = [];
      const mime = pickMime();
      clientLog(`MediaRecorder mime=${mime || "default"}`);
      const recorder = mime
        ? new MediaRecorder(this.stream, { mimeType: mime })
        : new MediaRecorder(this.stream);
      recorder.ondataavailable = (event) => {
        if (event.data?.size) this.chunks.push(event.data);
      };
      recorder.onstop = () => {
        clientLog("MediaRecorder.onstop fired");
        this._finalize();
      };
      recorder.onerror = (event) => clientLog(`MediaRecorder.onerror: ${event.error?.name || "unknown"}`);
      this.mediaRecorder = recorder;
      this.prepared = true;
    },
    begin() {
      if (!this.mediaRecorder) return;
      this.mediaRecorder.start(500);
      this.recording = true;
    },
    async start(onStop) {
      await this.prepare(onStop);
      this.begin();
    },
    stop() {
      if (!this.mediaRecorder || !this.recording) return;
      this.recording = false;
      try { this.mediaRecorder.requestData(); } catch (_) {}
      try { this.mediaRecorder.stop(); } catch (_) {}
      window.setTimeout(() => this._finalize(), 800);
    },
  };
}

export function makeTimer(elementId) {
  let interval = null;
  let elapsed = 0;
  const render = () => {
    const minutes = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const seconds = String(elapsed % 60).padStart(2, "0");
    document.getElementById(elementId).textContent = `${minutes}:${seconds}`;
  };
  return {
    start() {
      elapsed = 0;
      render();
      interval = window.setInterval(() => {
        elapsed += 1;
        render();
      }, 1000);
    },
    stop() {
      if (interval) window.clearInterval(interval);
      interval = null;
    },
  };
}

export function runCountdown(statusElement, seconds = 3, onTick) {
  return new Promise((resolve) => {
    let remaining = seconds;
    const tick = () => {
      statusElement.textContent = String(remaining);
      onTick?.(remaining);
      if (remaining <= 1) {
        window.setTimeout(resolve, 1000);
        return;
      }
      remaining -= 1;
      window.setTimeout(tick, 1000);
    };
    tick();
  });
}

export function setStatus(element, state, message) {
  element.className = `analyze-status${state ? ` ${state}` : ""}`;
  if (message != null) element.textContent = message;
}
