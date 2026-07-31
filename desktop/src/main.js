// NativeLingo frontend logic.
// Two top-level modules: Speaking (口语: video-shadowing + audio-upload) and
// Memorizing (识物: photo object labeling + scenario sentences, Phase D).
// Talks to the local FastAPI sidecar; backend URL + token injected by the Tauri
// shell, with dev fallbacks.

const BACKEND_URL = window.__NATIVELINGO_BACKEND__ || "http://127.0.0.1:8756";
const BACKEND_TOKEN = window.__NATIVELINGO_TOKEN__ || null;

// boot marker: confirms in the backend log which JS build loaded. Fired both at
// load (visible when the backend is already up from a prior session) and again
// once the backend responds, so the marker is reliable across cold starts (the
// load-time ping otherwise fails silently while the backend is still spinning
// up and never reaches the log).
const BOOT_TAG = "v19";
let _bootMarked = false;
function markBoot() {
  if (_bootMarked) return;
  fetch(`${BACKEND_URL}/health?boot=${BOOT_TAG}`)
    .then(() => { _bootMarked = true; })
    .catch(() => {});
}
markBoot();

// send a debug message to the backend log (webview has no visible console)
function clientLog(msg) {
  try {
    fetch(`${BACKEND_URL}/clientlog`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ msg: String(msg) }),
    }).catch(() => {});
  } catch (_) {}
}
window.addEventListener("error", (e) => clientLog("window.error: " + e.message));
window.addEventListener("unhandledrejection", (e) =>
  clientLog("unhandledrejection: " + (e.reason && e.reason.message ? e.reason.message : e.reason))
);

const $ = (id) => document.getElementById(id);
const authHeaders = () =>
  BACKEND_TOKEN ? { Authorization: `Bearer ${BACKEND_TOKEN}` } : {};
const tokenQS = () => (BACKEND_TOKEN ? `?token=${encodeURIComponent(BACKEND_TOKEN)}` : "");

// Memorizing actions should never leave a learner staring at an infinite
// spinner. The backend mirrors this deadline, but AbortController gives the
// UI a prompt, deterministic recovery path even if a local process wedges.
const MEMO_REQUEST_TIMEOUT_MS = 15_000;
async function memoFetch(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), MEMO_REQUEST_TIMEOUT_MS);
  try {
    return await fetch(`${BACKEND_URL}${path}`, { ...options, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) {
      const timeout = new Error("等待超过15秒，已停止本次请求。请重试；若持续发生，请重新打开应用。");
      timeout.name = "MemoTimeoutError";
      throw timeout;
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

// =====================================================================
// Backend health
// =====================================================================
async function checkBackend() {
  const status = $("backend-status");
  try {
    const res = await fetch(`${BACKEND_URL}/health`);
    const data = await res.json();
    if (data.status === "ok") {
      status.textContent = data.model_loaded ? "后端就绪" : "后端启动中(模型加载)…";
      status.className = "status status-ok";
      markBoot();   // now that the backend is up, the boot marker will reach the log
      return true;
    }
  } catch (_) {}
  status.textContent = "无法连接后端";
  status.className = "status status-error";
  return false;
}

// Background prefetch of the heavy analysis models (MMS + phoneme). The backend
// downloads them at startup so the first 分析 isn't a multi-GB blind wait; this
// polls /warmup and surfaces the stage. Polling stops once everything is ready.
let warmupState = null;
const _WARMUP_LABEL = { encoder: "编码器", mms: "MMS 对齐 ~1.2GB", phoneme: "音素 ~2.4GB" };
async function pollWarmup() {
  try {
    warmupState = await (await fetch(`${BACKEND_URL}/warmup`)).json();
  } catch (_) { return; }
  if (!warmupState) return;
  const st = $("backend-status");
  if (warmupState.stage === "done") {
    st.textContent = "后端就绪 · 分析模型就绪";
    st.className = "status status-ok";
    return;
  }
  st.textContent = `后端就绪 · 预下载分析模型(${_WARMUP_LABEL[warmupState.stage] || warmupState.stage})…`;
  st.className = "status status-pending";
  setTimeout(pollWarmup, 3000);
}

// =====================================================================
// Module + mode switching
// =====================================================================
// Top-level modules: Speaking vs Memorizing. Only one module-pane is visible
// at a time; the Speaking results section belongs to Speaking only.
document.querySelectorAll(".module").forEach((mod) => {
  mod.addEventListener("click", () => {
    const m = mod.dataset.module;
    document.querySelectorAll(".module").forEach((x) => x.classList.toggle("module-active", x === mod));
    document.querySelectorAll(".module-pane").forEach((p) => { p.hidden = p.id !== "module-" + m; });
    if (m !== "speaking") $("results").hidden = true;
    onModuleChange(m);
  });
});

// Speaking sub-tabs (video / audio). Scoped to the Speaking pane so the
// toggle generalizes if more Speaking modes are added later.
document.querySelectorAll("#module-speaking .tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll("#module-speaking .tab").forEach((t) => t.classList.remove("tab-active"));
    tab.classList.add("tab-active");
    const mode = tab.dataset.mode;
    document.querySelectorAll("#module-speaking .mode").forEach((m) => { m.hidden = m.id !== "mode-" + mode; });
    $("results").hidden = true;
  });
});

// Module lifecycle hook. Memorize warmup/release are wired in Phase D once the
// /memorize/* endpoints + this module's UI exist.
function onModuleChange(module) {
  if (module === "memorize") memoEnter();
  else memoLeave();
}

// =====================================================================
// Shared recording helper
// =====================================================================
function pickMime() {
  // WKWebView typically supports mp4/aac; Chromium supports webm/opus.
  const cands = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", ""];
  for (const c of cands) {
    if (c === "" || (window.MediaRecorder && MediaRecorder.isTypeSupported(c))) {
      return c;
    }
  }
  return "";
}

function createRecorder() {
  return {
    mediaRecorder: null,
    chunks: [],
    recording: false,
    prepared: false,
    blob: null,
    stream: null,
    _onStop: null,
    _finalize() {
      // guard against double-finalize (onstop + manual fallback)
      if (this._finalized) return;
      this._finalized = true;
      const type = (this.mediaRecorder && this.mediaRecorder.mimeType) || "audio/mp4";
      this.blob = new Blob(this.chunks, { type });
      clientLog("recorder finalize; chunks=" + this.chunks.length + " blob=" + this.blob.size);
      if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
      if (this._onStop) this._onStop(this.blob);
    },
    // Open the mic + build the MediaRecorder WITHOUT starting capture. Lets
    // the caller run a countdown between prepare() and begin() so the learner
    // has an unambiguous "start now" cue — the getUserMedia delay is absorbed
    // during the countdown, so nothing at the opening gets clipped.
    async prepare(onStop) {
      this._onStop = onStop;
      this._finalized = false;
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.chunks = [];
      const mime = pickMime();
      clientLog("MediaRecorder mime=" + (mime || "(default)"));
      const rec = mime ? new MediaRecorder(this.stream, { mimeType: mime })
                       : new MediaRecorder(this.stream);
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) this.chunks.push(e.data);
      };
      rec.onstop = () => { clientLog("MediaRecorder.onstop fired"); this._finalize(); };
      rec.onerror = (e) => clientLog("MediaRecorder.onerror: " + (e.error && e.error.name));
      this.mediaRecorder = rec;
      this.prepared = true;
    },
    // Start capture (call after prepare()). timeslice: flush data periodically
    // (WKWebView needs this to emit data).
    begin() {
      if (this.mediaRecorder) {
        this.mediaRecorder.start(500);
        this.recording = true;
      }
    },
    // Convenience: prepare + begin with no gap (legacy callers).
    async start(onStop) {
      await this.prepare(onStop);
      this.begin();
    },
    stop() {
      if (this.mediaRecorder && this.recording) {
        this.recording = false;
        try {
          this.mediaRecorder.requestData();  // force a final dataavailable
        } catch (_) {}
        try {
          this.mediaRecorder.stop();
        } catch (_) {}
        // fallback: if onstop doesn't fire within 800ms, finalize manually
        setTimeout(() => this._finalize(), 800);
      }
    },
  };
}

function makeTimer(elId) {
  let interval = null;
  let elapsed = 0;
  const render = () => {
    const m = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const s = String(elapsed % 60).padStart(2, "0");
    $(elId).textContent = `${m}:${s}`;
  };
  return {
    start() {
      elapsed = 0;
      render();
      interval = setInterval(() => {
        elapsed += 1;
        render();
      }, 1000);
    },
    stop() {
      if (interval) clearInterval(interval);
    },
  };
}

// Countdown shown in the status bar between mic-prepare and capture-start,
// giving the learner an unambiguous "start reading now" cue. Shows secs..1
// (one number per second), then resolves — capture should begin() at resolve.
function runCountdown(statusEl, secs = 3) {
  return new Promise((resolve) => {
    let n = secs;
    const tick = () => {
      statusEl.textContent = String(n);
      if (n <= 1) { setTimeout(resolve, 1000); return; }
      n -= 1;
      setTimeout(tick, 1000);
    };
    tick();
  });
}

// Swap the status bar's modifier class (prep / countdown / rec / "").
function setStatus(el, cls, msg) {
  el.className = "analyze-status" + (cls ? " " + cls : "");
  if (msg != null) el.textContent = msg;
}

// =====================================================================
// AUDIO MODE (original)
// =====================================================================
const audio = { referenceBlob: null, learnerBlob: null };
const audioRec = createRecorder();
const audioTimer = makeTimer("record-timer");

$("ref-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  audio.referenceBlob = file;
  const player = $("ref-player");
  player.src = URL.createObjectURL(file);
  player.hidden = false;
  audioUpdateBtn();
});

$("record-btn").addEventListener("click", async () => {
  const btn = $("record-btn");
  if (audioRec.recording) {
    audioRec.stop();
    audioTimer.stop();
    setStatus($("analyze-status"), "", "处理录音中…");
    btn.textContent = "● 开始录音";
    btn.classList.remove("recording");
  } else {
    try {
      const statusEl = $("analyze-status");
      setStatus(statusEl, "prep", "正在准备麦克风…");
      btn.disabled = true;
      btn.textContent = "准备中…";
      await audioRec.prepare((blob) => {
        audio.learnerBlob = blob;
        const player = $("learner-player");
        player.src = URL.createObjectURL(blob);
        player.hidden = false;
        audioUpdateBtn();
        setStatus(statusEl, "", "录制完成,可点击“分析我的发音”");
      });
      setStatus(statusEl, "countdown");
      await runCountdown(statusEl, 3);
      audioRec.begin();
      audioTimer.start();
      setStatus(statusEl, "rec", "正在录音,请开始朗读");
      btn.disabled = false;
      btn.textContent = "■ 停止录音";
      btn.classList.add("recording");
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "● 开始录音";
      setStatus($("analyze-status"), "", "无法访问麦克风: " + (err.message || err));
    }
  }
});

function audioUpdateBtn() {
  $("analyze-btn").disabled = !(audio.referenceBlob && audio.learnerBlob);
}

$("analyze-btn").addEventListener("click", async () => {
  const statusEl = $("analyze-status");
  const btn = $("analyze-btn");
  btn.disabled = true;
  statusEl.textContent = "分析中,请稍候…";
  const form = new FormData();
  form.append("reference", audio.referenceBlob, "reference");
  form.append("learner", audio.learnerBlob, "learner.webm");
  try {
    const res = await fetch(`${BACKEND_URL}/analyze`, {
      method: "POST", body: form, headers: authHeaders(),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "分析失败");
    renderResults(await res.json());
    statusEl.textContent = "";
  } catch (err) {
    statusEl.textContent = "错误: " + err.message;
  } finally {
    btn.disabled = false;
    audioUpdateBtn();
  }
});

// =====================================================================
// VIDEO MODE
// =====================================================================
const videoState = {
  name: null,
  sentences: [],
  rangeStart: null,
  rangeEnd: null,
  learnerBlob: null,
  learnerUrl: null,
  learnerRid: null,   // server-side recording id (FR-8: exact WAV clip replay)
};
const shadowRec = createRecorder();
const shadowTimer = makeTimer("shadow-timer");

async function loadVideoList() {
  const container = $("video-list");
  try {
    const res = await fetch(`${BACKEND_URL}/videos`, { headers: authHeaders() });
    const data = await res.json();
    if (!data.videos || data.videos.length === 0) {
      container.innerHTML = '<div class="hint">videos/ 目录下暂无视频。放入 .mp4 后刷新。</div>';
      return;
    }
    container.innerHTML = "";
    data.videos.forEach((v) => {
      const item = document.createElement("div");
      item.className = "video-item";
      item.innerHTML = `<span>${v.name}</span><span class="meta">${v.size_mb} MB</span>`;
      item.addEventListener("click", () => selectVideo(v.name, item));
      container.appendChild(item);
    });
  } catch (err) {
    container.innerHTML = `<div class="hint">加载失败: ${err.message}</div>`;
  }
}

async function selectVideo(name, itemEl) {
  document.querySelectorAll(".video-item").forEach((el) => el.classList.remove("selected"));
  itemEl.classList.add("selected");
  videoState.name = name;
  videoState.rangeStart = null;
  videoState.rangeEnd = null;

  const sentSection = $("sentence-section");
  const list = $("sentence-list");
  sentSection.hidden = false;
  $("shadow-section").hidden = true;
  list.innerHTML = '<div class="hint">转写并切分句子中(首次较慢,请稍候)…</div>';
  $("range-info").textContent = "转写中…";

  try {
    const res = await fetch(`${BACKEND_URL}/videos/${encodeURIComponent(name)}/process`, {
      method: "POST", headers: authHeaders(),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "转写失败");
    const data = await res.json();
    videoState.sentences = data.sentences;
    renderSentences();
  } catch (err) {
    list.innerHTML = `<div class="hint">转写失败: ${err.message}</div>`;
    $("range-info").textContent = "出错";
  }
}

function fmt(t) {
  const m = String(Math.floor(t / 60)).padStart(2, "0");
  const s = String(Math.floor(t % 60)).padStart(2, "0");
  return `${m}:${s}`;
}

function renderSentences() {
  const list = $("sentence-list");
  list.innerHTML = "";
  videoState.sentences.forEach((sent) => {
    const item = document.createElement("div");
    item.className = "sentence-item";
    item.dataset.index = sent.index;
    item.innerHTML =
      `<span class="idx">${sent.index + 1}.</span>` +
      `<span class="ts">${fmt(sent.start)}</span>` +
      `<span class="txt">${sent.text}</span>`;
    item.addEventListener("click", () => pickSentence(sent.index));
    list.appendChild(item);
  });
  updateRangeUI();
}

function pickSentence(idx) {
  const st = videoState;
  if (st.rangeStart === null || st.rangeEnd !== null) {
    // start a new selection
    st.rangeStart = idx;
    st.rangeEnd = null;
  } else {
    // set the end
    st.rangeEnd = idx;
    if (st.rangeEnd < st.rangeStart) {
      [st.rangeStart, st.rangeEnd] = [st.rangeEnd, st.rangeStart];
    }
  }
  updateRangeUI();
}

function updateRangeUI() {
  const st = videoState;
  const start = st.rangeStart;
  const end = st.rangeEnd !== null ? st.rangeEnd : st.rangeStart;
  document.querySelectorAll(".sentence-item").forEach((el) => {
    const i = parseInt(el.dataset.index, 10);
    el.classList.remove("in-range", "endpoint");
    if (start === null) return;
    if (i === start || i === end) el.classList.add("endpoint");
    else if (i > start && i < end) el.classList.add("in-range");
  });

  const info = $("range-info");
  if (start === null) {
    info.textContent = "尚未选择";
    $("shadow-section").hidden = true;
    return;
  }
  const s = st.sentences[start];
  const e = st.sentences[end];
  const count = end - start + 1;
  info.textContent =
    st.rangeEnd === null
      ? `已选起始:第 ${start + 1} 句 — 再点一句设为结束(或直接开始跟读单句)`
      : `已选:第 ${start + 1} — ${end + 1} 句 (共 ${count} 句, ${fmt(s.start)}–${fmt(e.end)})`;

  // show the shadow section once at least a start is chosen
  setupShadow(s.start, e.end);
}

// ---- shadow recording with synchronized muted video ----
let shadowEndTime = 0;
let shadowStartTime = 0;

function setupShadow(startT, endT) {
  shadowStartTime = startT;
  shadowEndTime = endT;
  $("shadow-section").hidden = false;
  const video = $("shadow-video");
  const src = `${BACKEND_URL}/videos/${encodeURIComponent(videoState.name)}/stream${tokenQS()}`;
  if (video.dataset.src !== src) {
    video.src = src;
    video.dataset.src = src;
  }
  // seek to the start once metadata is ready so the first frame previews
  const seek = () => { try { video.currentTime = startT; } catch (_) {} };
  if (video.readyState >= 1) seek();
  else video.addEventListener("loadedmetadata", seek, { once: true });
  $("shadow-analyze-btn").disabled = true;
  $("shadow-learner-player").hidden = true;
}

function playShadowClip() {
  const video = $("shadow-video");
  video.muted = true;
  video.currentTime = shadowStartTime;
  video.play().catch(() => {});
  const onTick = () => {
    if (video.currentTime >= shadowEndTime) {
      video.pause();
      video.removeEventListener("timeupdate", onTick);
    }
  };
  video.addEventListener("timeupdate", onTick);
}

$("shadow-replay-btn").addEventListener("click", playShadowClip);

function shadowStatus(msg) {
  setStatus($("shadow-analyze-status"), "", msg);
}

$("shadow-record-btn").addEventListener("click", async () => {
  clientLog("shadow-record-btn clicked; recording=" + shadowRec.recording);
  const btn = $("shadow-record-btn");
  if (shadowRec.recording) {
    shadowRec.stop();
    shadowTimer.stop();
    $("shadow-video").pause();
    btn.textContent = "● 开始跟读";
    btn.classList.remove("recording");
    shadowStatus("处理录音中…");
  } else {
    if (videoState.rangeStart === null) {
      shadowStatus("请先选择要跟读的句子");
      return;
    }
    clientLog("mediaDevices exists=" + !!(navigator.mediaDevices) +
      " getUserMedia=" + !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia));
    try {
      const statusEl = $("shadow-analyze-status");
      setStatus(statusEl, "prep", "正在准备麦克风…");
      btn.disabled = true;
      btn.textContent = "准备中…";
      await shadowRec.prepare((blob) => {
        clientLog("recording stopped; blob size=" + blob.size);
        videoState.learnerBlob = blob;
        videoState.learnerRid = null;
        if (videoState.learnerUrl) URL.revokeObjectURL(videoState.learnerUrl);
        videoState.learnerUrl = URL.createObjectURL(blob);
        const player = $("shadow-learner-player");
        player.src = videoState.learnerUrl;
        player.hidden = false;
        $("shadow-analyze-btn").disabled = false;
        shadowStatus(blob.size > 0 ? "录制完成,可点击“分析我的发音”" : "录音为空,请重试");
        uploadLearnerRecording(blob);
      });
      clientLog("getUserMedia succeeded; recorder prepared");
      // Countdown gives a clear "start now" cue. Capture + video begin
      // together at zero, so the opening isn't clipped and there's no
      // lead-in silence to skew alignment/fluency.
      setStatus(statusEl, "countdown");
      await runCountdown(statusEl, 3);
      shadowRec.begin();
      playShadowClip(); // muted video + subtitles play in sync, from rangeStart
      shadowTimer.start();
      setStatus(statusEl, "rec", "正在录音,请开始朗读");
      btn.disabled = false;
      btn.textContent = "■ 停止跟读";
      btn.classList.add("recording");
    } catch (err) {
      clientLog("getUserMedia FAILED: " + (err && err.name) + " / " + (err && err.message));
      btn.disabled = false;
      btn.textContent = "● 开始跟读";
      shadowStatus("无法访问麦克风: " + (err && err.message ? err.message : err));
    }
  }
});

$("shadow-analyze-btn").addEventListener("click", async () => {
  const statusEl = $("shadow-analyze-status");
  const btn = $("shadow-analyze-btn");
  btn.disabled = true;
  statusEl.textContent = (warmupState && warmupState.stage !== "done")
    ? `首次需下载分析模型(预拉中:${warmupState.stage}),请稍候…`
    : "分析中,请稍候…";
  const st = videoState;
  const end = st.rangeEnd !== null ? st.rangeEnd : st.rangeStart;
  const form = new FormData();
  form.append("video", st.name);
  form.append("start_index", st.rangeStart);
  form.append("end_index", end);
  form.append("learner", st.learnerBlob, "learner.webm");
  try {
    const res = await fetch(`${BACKEND_URL}/analyze_video`, {
      method: "POST", body: form, headers: authHeaders(),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "分析失败");
    renderResults(await res.json());
    statusEl.textContent = "";
  } catch (err) {
    statusEl.textContent = "错误: " + err.message;
  } finally {
    btn.disabled = false;
  }
});

// =====================================================================
// Shared results rendering
// =====================================================================
function bandColor(score) {
  if (score >= 75) return "var(--good)";
  if (score >= 60) return "var(--fair)";
  return "var(--bad)";
}

function renderResults(data) {
  $("results").hidden = false;

  const refText = $("reference-text");
  if (data.reference_text) {
    refText.textContent = "参考文本: " + data.reference_text;
    refText.hidden = false;
  } else {
    refText.hidden = true;
  }

  const set = (id, val) => {
    const el = $(id);
    el.textContent = Math.round(val);
    el.style.color = bandColor(val);
  };
  set("overall-score", data.overall_score);
  set("accuracy-score", data.accuracy);
  set("fluency-score", data.fluency);

  const ratio = data.speech_rate_ratio;
  let rateText = `语速比(你/参考): ${ratio.toFixed(2)}×`;
  if (ratio > 1.15) rateText += " — 偏慢";
  else if (ratio < 0.85) rateText += " — 偏快";
  else rateText += " — 接近参考";
  $("rate-info").textContent = rateText;

  const tipsList = $("tips-list");
  tipsList.innerHTML = "";
  (data.tips || []).forEach((tip) => {
    const li = document.createElement("li");
    li.textContent = tip;
    tipsList.appendChild(li);
  });

  const prosody = data.prosody;
  if (prosody) {
    $("prosody-info").innerHTML =
      `语调匹配: <span>${Math.round(prosody.intonation_match)}</span> · ` +
      `停顿匹配: <span>${Math.round(prosody.pause_match)}</span> · ` +
      `你的停顿次数: <span>${prosody.learner_pauses}</span> (参考 ${prosody.reference_pauses})`;
  }

  renderSentenceDetails(data.sentences, data.segment);
  $("results").scrollIntoView({ behavior: "smooth" });
}

function renderSentenceDetails(sentences, segment) {
  const block = $("detail-block");
  const container = $("sentence-details");
  if (!sentences || !sentences.length) {
    block.hidden = true;
    return;
  }
  block.hidden = false;
  container.innerHTML = "";

  // point the learner clip player at the current recording (if any)
  const myPlayer = $("my-clip-player");
  if (myPlayer && videoState.learnerUrl && myPlayer.src !== videoState.learnerUrl) {
    myPlayer.src = videoState.learnerUrl;
  }

  sentences.forEach((sd) => {
    const card = document.createElement("div");
    card.className = "sent-detail";

    const head = document.createElement("div");
    head.className = "sent-head";
    const scores = document.createElement("span");
    scores.className = "sent-scores";
    scores.innerHTML =
      `准确度 <span style="color:${bandColor(sd.accuracy)}">${Math.round(sd.accuracy)}</span> · ` +
      `流畅度 <span style="color:${bandColor(sd.fluency)}">${Math.round(sd.fluency)}</span>`;
    head.appendChild(scores);

    // in-place clip playback: original reference audio + your own recording,
    // no video, no scroll.
    const btns = document.createElement("span");
    btns.className = "sent-btns";
    if (segment && videoState.name) {
      const absStart = segment.start + sd.start;
      const absEnd = segment.start + sd.end;
      const refBtn = document.createElement("button");
      refBtn.className = "sent-play";
      refBtn.textContent = "▶ 原声";
      refBtn.title = "播放此句参考原声";
      refBtn.addEventListener("click", () => playRefClip(absStart, absEnd));
      btns.appendChild(refBtn);
    }
    if (videoState.learnerUrl && sd.learner_end > sd.learner_start) {
      const myBtn = document.createElement("button");
      myBtn.className = "sent-play sent-play-mine";
      myBtn.textContent = "▶ 我的录音";
      myBtn.title = "播放你自己读这句的录音";
      myBtn.addEventListener("click", () => playMyClip(sd.learner_start, sd.learner_end));
      btns.appendChild(myBtn);
    }
    head.appendChild(btns);
    card.appendChild(head);

    const wordsEl = document.createElement("div");
    wordsEl.className = "sent-words";
    sd.words.forEach((w) => {
      const span = document.createElement("span");
      span.className = "word w-" + w.status + (w.tip ? " has-tip" : "");
      span.textContent = w.word + " ";
      span.title = w.tip ? w.tip : `准确度 ${Math.round(w.accuracy)}`;
      wordsEl.appendChild(span);
    });
    card.appendChild(wordsEl);

    // per-word improvement directions with A/B (reference vs your) replay
    const tipped = sd.words.filter((w) => w.tip);
    if (tipped.length) {
      const tipsEl = document.createElement("div");
      tipsEl.className = "word-tips";
      tipped.forEach((w) => {
        const row = document.createElement("div");
        row.className = "word-tip";

        const label = document.createElement("span");
        label.className = "word w-" + w.status + " wt-label";
        label.textContent = w.word;
        row.appendChild(label);

        const txt = document.createElement("span");
        txt.className = "wt-text";
        txt.textContent = w.tip;
        row.appendChild(txt);

        const ab = document.createElement("span");
        ab.className = "wt-ab";
        if (segment && videoState.name) {
          const rb = document.createElement("button");
          rb.className = "wt-btn";
          rb.textContent = "🔊 原声";
          rb.title = "只听原声这个词";
          rb.addEventListener("click", () =>
            playRefClip(segment.start + w.start, segment.start + w.end));
          ab.appendChild(rb);
        }
        if (videoState.learnerUrl && w.learner_end > w.learner_start) {
          const mb = document.createElement("button");
          mb.className = "wt-btn wt-btn-mine";
          mb.textContent = "🔊 我的";
          mb.title = "只听你自己这个词";
          mb.addEventListener("click", () => playMyClip(w.learner_start, w.learner_end));
          ab.appendChild(mb);
        }
        row.appendChild(ab);
        tipsEl.appendChild(row);
      });
      card.appendChild(tipsEl);
    }
    container.appendChild(card);
  });
}

// stop any clip / video that might currently be playing
function stopAllClips() {
  ["ref-clip-player", "my-clip-player", "shadow-video"].forEach((id) => {
    const el = $(id);
    if (el) { try { el.pause(); } catch (_) {} }
  });
}

// ASR word-end timestamps run slightly early, so the reference clip would cut
// off the tail of the last word. Pad the end a little to let it finish.
const REF_CLIP_TAIL_PAD = 0.1;

// play a single sentence's *reference* audio in place (no video, no scroll).
// The backend returns an exact-length WAV, so we just play it start-to-finish.
function playRefClip(absStart, absEnd) {
  stopAllClips();
  const a = $("ref-clip-player");
  if (!a) return;
  const tok = BACKEND_TOKEN ? `&token=${encodeURIComponent(BACKEND_TOKEN)}` : "";
  a.src =
    `${BACKEND_URL}/videos/${encodeURIComponent(videoState.name)}/clip` +
    `?start=${absStart.toFixed(3)}&end=${(absEnd + REF_CLIP_TAIL_PAD).toFixed(3)}${tok}`;
  a.currentTime = 0;
  a.play().catch((e) => clientLog("refClip play failed: " + (e && e.message)));
}

// play the learner's own recording for a sentence/word.
// Preferred path (FR-8): the backend cuts an exact WAV slice from the stored
// recording — sample-accurate, no ~250 ms timeupdate truncation. Falls back to
// seeking inside the local blob if the server-side recording isn't ready yet.
function playMyClip(startT, endT) {
  stopAllClips();
  const a = $("my-clip-player");
  if (!a) return;
  if (videoState.learnerRid) {
    const tok = BACKEND_TOKEN ? `&token=${encodeURIComponent(BACKEND_TOKEN)}` : "";
    a.src =
      `${BACKEND_URL}/recordings/${videoState.learnerRid}/clip` +
      `?start=${startT.toFixed(3)}&end=${endT.toFixed(3)}${tok}`;
    a.currentTime = 0;
    a.play().catch((e) => clientLog("myClip play failed: " + (e && e.message)));
    return;
  }
  if (!a.src) { clientLog("playMyClip: no learner clip src"); return; }
  const doPlay = () => {
    try { a.currentTime = startT; } catch (_) {}
    a.play().catch((e) => clientLog("myClip play failed: " + (e && e.message)));
    const onTick = () => {
      if (a.currentTime >= endT) {
        a.pause();
        a.removeEventListener("timeupdate", onTick);
      }
    };
    a.addEventListener("timeupdate", onTick);
  };
  if (a.readyState >= 1) doPlay();
  else a.addEventListener("loadedmetadata", doPlay, { once: true });
}

// store the learner recording server-side so word/sentence replay can be cut
// as exact WAV slices (same mechanism as the reference /clip endpoint).
async function uploadLearnerRecording(blob) {
  try {
    const form = new FormData();
    form.append("learner", blob, "learner.webm");
    const res = await fetch(`${BACKEND_URL}/recordings`, {
      method: "POST", body: form, headers: authHeaders(),
    });
    if (!res.ok) throw new Error(`status ${res.status}`);
    const data = await res.json();
    // only adopt if the user hasn't re-recorded in the meantime
    if (videoState.learnerBlob === blob) {
      videoState.learnerRid = data.recording_id;
      clientLog("learner recording stored: " + data.recording_id);
    }
  } catch (err) {
    clientLog("recording upload failed (clip replay will use blob seek): " +
      (err && err.message));
  }
}

// =====================================================================
// MEMORIZE MODULE (看图识物: FR-13/14/15)
// =====================================================================
// Upload a photo -> whole-object detection with clickable hotspots (FR-13) ->
// click an object -> zoom into its parts (FR-14) + scenario example sentences
// (FR-15). All recognition is on-device (NFR-5). Photos are re-encoded to JPEG
// via <canvas> before upload so iOS HEIC (which Pillow can't decode) and huge
// files are handled, and the displayed image dims match what the backend saw.
const memo = {
  entered: false,
  warmupTimer: null,
  imgEl: null,
  imgW: 0, imgH: 0,        // pixel dims of the uploaded (canvas-reencoded) image
  photoId: null,
  objects: [],
  recognitionToken: 0,
  detailToken: 0,
  scenarioToken: 0,
};
const MEMO_MAX_DIM = 1920;
const _MEMO_STAGE_LABEL = {
  yolo: "YOLO 检测模型",
  llm: "Qwen Q4_K_M 情景模型 ~491MB",
  florence: "Florence 视觉增强模型 ~463MB",
};

function memoStatus(cls, msg) {
  const el = $("memo-status");
  if (!msg) { el.className = "memo-status"; el.textContent = ""; return; }
  el.className = "memo-status show" + (cls ? " " + cls : "");
  el.textContent = msg;
}

// ---- on-demand model lifecycle: prefetch on tab-enter, free on tab-leave ----
async function memoEnter() {
  if (memo.entered) return;
  memo.entered = true;
  try {
    await memoFetch("/memorize/warmup", { method: "POST", headers: authHeaders() });
  } catch (_) { /* backend not up yet; status poll will retry softly */ }
  memoPollStatus();
}

async function memoLeave() {
  if (!memo.entered) return;
  memo.entered = false;
  memo.detailToken += 1;
  memo.scenarioToken += 1;
  if (memo.warmupTimer) { clearTimeout(memo.warmupTimer); memo.warmupTimer = null; }
  try {
    await memoFetch("/memorize/release", { method: "POST", headers: authHeaders() });
  } catch (_) {}
}

async function memoPollStatus() {
  try {
    const st = await (await memoFetch("/memorize/status", { headers: authHeaders() })).json();
    const busy = st.running || (st.stage && !["done", "idle", "error"].includes(st.stage));
    if (st.stage === "error") {
      memoStatus("err", "模型准备出错:" + (st.error || "") + "(仍可尝试,将按需下载)");
    } else if (busy) {
      memoStatus("", `正在准备${_MEMO_STAGE_LABEL[st.stage] || st.stage}…(首次需下载,请稍候)`);
    } else {
      memoStatus("", "");  // ready / idle -> hide
    }
    if (busy) memo.warmupTimer = setTimeout(memoPollStatus, 2500);
  } catch (_) { /* backend mid-start; retry lazily on next entry */ }
}

// ---- upload + recognition ----
function memoWireUpload() {
  const zone = $("memo-upload");
  const input = $("memo-file");
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault(); zone.classList.remove("drag");
    const f = e.dataTransfer.files[0]; if (f) memoHandleFile(f);
  });
  input.addEventListener("change", (e) => {
    const f = e.target.files[0]; if (f) memoHandleFile(f); input.value = "";
  });
  $("memo-reupload").addEventListener("click", memoResetToUpload);
  $("memo-back").addEventListener("click", () => {
    $("memo-detail").hidden = true;
    $("memo-view").scrollIntoView({ behavior: "smooth" });
  });
}

function memoResetToUpload() {
  $("memo-view").hidden = true;
  $("memo-detail").hidden = true;
  $("memo-upload").closest(".card").hidden = false;
  memo.objects = []; memo.photoId = null;
  memo.recognitionToken += 1;
  memo.detailToken += 1;
  memo.scenarioToken += 1;
  $("memo-hotspots").innerHTML = "";
  $("memo-object-summary").hidden = true;
  $("memo-object-summary").textContent = "";
}

// Re-encode any decodable image (incl. iOS HEIC if the system decodes it) to a
// size-capped JPEG via <canvas>. Returns {blob, w, h}.
function memoReencode(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const im = new Image();
    im.onload = () => {
      URL.revokeObjectURL(url);
      let w = im.naturalWidth, h = im.naturalHeight;
      const scale = Math.min(1, MEMO_MAX_DIM / Math.max(w, h));
      w = Math.max(1, Math.round(w * scale)); h = Math.max(1, Math.round(h * scale));
      const c = document.createElement("canvas");
      c.width = w; c.height = h;
      c.getContext("2d").drawImage(im, 0, 0, w, h);
      c.toBlob((b) => (b ? resolve({ blob: b, w, h }) : reject(new Error("encode"))),
               "image/jpeg", 0.9);
    };
    im.onerror = () => { URL.revokeObjectURL(url); reject(new Error("decode")); };
    im.src = url;
  });
}

async function memoHandleFile(file) {
  const recognitionToken = ++memo.recognitionToken;
  let enc;
  try { enc = await memoReencode(file); }
  catch (e) { memoStatus("err", "无法读取该图片,请换一张(JPG/PNG/HEIC)。"); return; }

  $("memo-upload").closest(".card").hidden = true;
  $("memo-detail").hidden = true;
  const view = $("memo-view"); view.hidden = false;
  const img = $("memo-img");
  img.src = URL.createObjectURL(enc.blob);
  memo.imgEl = img;
  memo.imgW = enc.w; memo.imgH = enc.h;
  $("memo-hotspots").innerHTML = "";
  $("memo-object-summary").hidden = true;
  $("memo-object-summary").textContent = "";
  $("memo-analyzing").hidden = false;

  try {
    const form = new FormData();
    form.append("photo", enc.blob, "photo.jpg");
    const res = await memoFetch("/memorize/analyze", {
      method: "POST", body: form, headers: authHeaders(),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "识别失败");
    if (recognitionToken !== memo.recognitionToken) return;
    memo.photoId = data.photo_id;
    memo.objects = data.objects || [];
    memoRenderHotspots();
  } catch (e) {
    if (recognitionToken !== memo.recognitionToken) return;
    memoStatus("err", "识别失败:" + e.message);
  } finally {
    // CSS explicitly honors the hidden attribute, and the token means an
    // earlier upload cannot hide the spinner belonging to a newer one.
    if (recognitionToken === memo.recognitionToken) {
      $("memo-analyzing").hidden = true;
    }
  }
}

function memoRenderHotspots() {
  const hs = $("memo-hotspots");
  const summary = $("memo-object-summary");
  hs.innerHTML = "";
  if (!memo.objects.length) {
    summary.hidden = true;
    summary.textContent = "";
    memoStatus("warn", "没有识别到明确的物品。试试物品更突出、更居中的照片。");
    return;
  }
  memoStatus("", "");  // clear any prior warn
  // Vocabulary surfaces deliberately stay English-only. Chinese is reserved
  // for complete scenario-sentence translations, avoiding a translation bridge.
  const counts = new Map();
  memo.objects.forEach((object) => {
    counts.set(object.label_en, (counts.get(object.label_en) || 0) + 1);
  });
  summary.textContent = `识别到 ${memo.objects.length} 个：` +
    [...counts.entries()].map(([label, count]) =>
      `${label}${count > 1 ? ` ×${count}` : ""}`,
    ).join(" · ");
  summary.hidden = false;

  // Large container boxes go below their contained objects. This keeps a
  // cabinet/showcase from covering a plaque, book or trophy hotspot.
  const renderObjects = [...memo.objects].sort((first, second) => {
    const firstArea = first.box[2] * first.box[3];
    const secondArea = second.box[2] * second.box[3];
    return secondArea - firstArea;
  });
  renderObjects.forEach((o) => {
    const [x, y, w, h] = o.box;
    const dot = document.createElement("div");
    dot.className = "hotspot";
    dot.style.left = (x / memo.imgW * 100) + "%";
    dot.style.top = (y / memo.imgH * 100) + "%";
    dot.style.width = (w / memo.imgW * 100) + "%";
    dot.style.height = (h / memo.imgH * 100) + "%";
    const areaRatio = (w * h) / Math.max(1, memo.imgW * memo.imgH);
    dot.style.zIndex = String(Math.max(1, 1000 - Math.round(areaRatio * 1000)));
    const tag = document.createElement("div");
    tag.className = "hotspot-tag";
    if (y / memo.imgH < 0.055) tag.classList.add("hotspot-tag-inside");
    if (x / memo.imgW > 0.72) tag.classList.add("hotspot-tag-right");
    tag.textContent = o.label_en;
    tag.title = o.label_en;
    dot.appendChild(tag);
    dot.addEventListener("click", () => memoOpenDetail(o));
    hs.appendChild(dot);
  });
}

function memoContextCropBox(obj) {
  const [x, y, w, h] = obj.box.map(Number);
  const cx = x + w / 2;
  const cy = y + h / 2;
  const contextW = w * 1.2;
  const contextH = h * 1.2;
  const left = Math.max(0, Math.trunc(cx - contextW / 2));
  const top = Math.max(0, Math.trunc(cy - contextH / 2));
  const right = Math.min(memo.imgW, Math.trunc(cx + contextW / 2));
  const bottom = Math.min(memo.imgH, Math.trunc(cy + contextH / 2));
  return [left, top, Math.max(1, right - left), Math.max(1, bottom - top)];
}

function memoDrawDetailCrop(cropBox) {
  const [x, y, w, h] = cropBox.map((value) => Math.round(Number(value)));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, w);
  canvas.height = Math.max(1, h);
  canvas.getContext("2d").drawImage(
    memo.imgEl, x, y, w, h, 0, 0, canvas.width, canvas.height,
  );
  $("memo-detail-img").src = canvas.toDataURL("image/jpeg", 0.9);
  return [canvas.width, canvas.height];
}

function memoPartBox(part, cropSize) {
  if (!Array.isArray(part.box) || part.box.length !== 4) return null;
  const values = part.box.map(Number);
  if (values.some((value) => !Number.isFinite(value))) return null;
  const [cropW, cropH] = cropSize;
  const x1 = Math.max(0, Math.min(cropW, values[0]));
  const y1 = Math.max(0, Math.min(cropH, values[1]));
  const x2 = Math.max(0, Math.min(cropW, values[2]));
  const y2 = Math.max(0, Math.min(cropH, values[3]));
  if (x2 - x1 < 2 || y2 - y1 < 2) return null;
  return [x1, y1, x2 - x1, y2 - y1];
}

function memoRenderPartHotspots(parts, cropSize, onSelect, chipByPart) {
  const layer = $("memo-part-hotspots");
  layer.replaceChildren();
  const hotspotByPart = new Map();
  const [cropW, cropH] = cropSize;

  parts.forEach((part) => {
    const box = memoPartBox(part, cropSize);
    if (!box) return;
    const [x, y, w, h] = box;
    const hotspot = document.createElement("button");
    hotspot.type = "button";
    const isContent = part.kind === "content";
    hotspot.className = "part-hotspot" + (isContent ? " content-hotspot" : "");
    hotspot.style.left = `${x / cropW * 100}%`;
    hotspot.style.top = `${y / cropH * 100}%`;
    hotspot.style.width = `${w / cropW * 100}%`;
    hotspot.style.height = `${h / cropH * 100}%`;
    const areaRatio = (w * h) / Math.max(1, cropW * cropH);
    hotspot.style.zIndex = String(Math.max(1, 1000 - Math.round(areaRatio * 1000)));

    const tag = document.createElement("span");
    tag.className = "part-hotspot-tag";
    if (y / cropH < 0.075) tag.classList.add("part-hotspot-tag-inside");
    if (x / cropW > 0.68) tag.classList.add("part-hotspot-tag-right");
    tag.textContent = part.label_en;
    hotspot.appendChild(tag);
    hotspot.setAttribute(
      "aria-label",
      `${isContent ? "选择内容物" : "选择部件"} ${tag.textContent}`,
    );
    hotspot.title = `点击生成 ${tag.textContent} 的情景对话`;
    hotspot.addEventListener("click", () => onSelect(part));
    hotspot.addEventListener("mouseenter", () => chipByPart.get(part)?.classList.add("preview"));
    hotspot.addEventListener("mouseleave", () => chipByPart.get(part)?.classList.remove("preview"));
    layer.appendChild(hotspot);
    hotspotByPart.set(part, hotspot);
  });
  return hotspotByPart;
}

async function memoOpenDetail(obj) {
  const detailToken = ++memo.detailToken;
  memo.scenarioToken += 1;
  const detail = $("memo-detail");
  detail.hidden = false;
  detail.scrollIntoView({ behavior: "smooth" });

  // Match the backend's +10% context crop. Florence's part boxes are xyxy
  // coordinates within this crop, so the same pixels must be shown here.
  let detailCropSize;
  try {
    detailCropSize = memoDrawDetailCrop(memoContextCropBox(obj));
  } catch (e) {
    $("memo-detail-img").src = memo.imgEl.src;
    detailCropSize = [memo.imgW, memo.imgH];
  }
  $("memo-part-hotspots").replaceChildren();
  $("memo-parts-analyzing").hidden = false;
  const detailLabel = $("memo-detail-label");
  detailLabel.replaceChildren(document.createTextNode(obj.label_en));

  // FR-14: parts
  const partsEl = $("memo-parts"); partsEl.replaceChildren();
  const contentsEl = $("memo-contents"); contentsEl.replaceChildren();
  const contentsSection = $("memo-contents-section");
  contentsSection.hidden = true;
  setStatus($("memo-parts-status"), "prep", "正在分析部件和可见内容物…");
  let analyzedParts = [];
  let analyzedContents = [];
  let isContainer = false;
  try {
    const res = await memoFetch("/memorize/parts", {
      method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({
        photo_id: memo.photoId, object_id: obj.id,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "部件识别失败");
    if (detailToken !== memo.detailToken) return;
    analyzedParts = (data.parts || []).map((part) => ({ ...part, kind: "part" }));
    analyzedContents = (data.contents || []).map((item) => ({
      ...item,
      kind: "content",
    }));
    isContainer = Boolean(data.is_container);
    if (Array.isArray(data.crop_box) && data.crop_box.length === 4) {
      try {
        detailCropSize = memoDrawDetailCrop(data.crop_box);
      } catch (_) { /* keep the locally computed matching crop */ }
    } else if (Array.isArray(data.crop_size) && data.crop_size.length === 2) {
      detailCropSize = data.crop_size.map(Number);
    }
  } catch (e) {
    if (detailToken !== memo.detailToken) return;
    setStatus($("memo-parts-status"), "", "部件识别失败:" + e.message);
  } finally {
    if (detailToken === memo.detailToken) $("memo-parts-analyzing").hidden = true;
  }

  contentsSection.hidden = !isContainer;
  const chipByPart = new Map();
  let hotspotByPart = new Map();
  const selectPart = (part) => {
    detail.querySelectorAll(".part-chip").forEach((item) => {
      item.classList.toggle("active", item === chipByPart.get(part));
    });
    $("memo-part-hotspots").querySelectorAll(".part-hotspot").forEach((item) => {
      item.classList.toggle("active", item === hotspotByPart.get(part));
    });
    memoGenerateScenario(obj, part.whole ? null : part);
  };
  const addChip = (part, parent, label, active = false) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "part-chip" +
      (part.kind === "content" ? " content-chip" : "") +
      (active ? " active" : "");
    chip.appendChild(document.createTextNode(label));
    chip.addEventListener("click", () => selectPart(part));
    chip.addEventListener("mouseenter", () => hotspotByPart.get(part)?.classList.add("preview"));
    chip.addEventListener("mouseleave", () => hotspotByPart.get(part)?.classList.remove("preview"));
    parent.appendChild(chip);
    chipByPart.set(part, chip);
  };
  const whole = {
    label_en: obj.label_en,
    label_zh: obj.label_zh,
    whole: true,
    kind: "whole",
  };
  addChip(whole, partsEl, `整件 · ${obj.label_en}`, true);
  analyzedParts.forEach((part) => addChip(part, partsEl, part.label_en));
  analyzedContents.forEach((item) => addChip(item, contentsEl, item.label_en));

  hotspotByPart = memoRenderPartHotspots(
    [...analyzedContents, ...analyzedParts],
    detailCropSize,
    selectPart,
    chipByPart,
  );
  const locatedCount = hotspotByPart.size;
  const detailCount = analyzedParts.length + analyzedContents.length;
  if (detailCount && locatedCount) {
    setStatus(
      $("memo-parts-status"), "",
      `识别到 ${analyzedContents.length} 个内容物、${analyzedParts.length} 个部件，` +
      `${locatedCount} 个已在图中标注。`,
    );
  } else if (detailCount) {
    setStatus(
      $("memo-parts-status"), "",
      `识别到 ${detailCount} 个可见细节，但当前没有可靠位置框。`,
    );
  } else {
    setStatus($("memo-parts-status"), "", "");
  }
  if (!analyzedParts.length) {
    const hint = document.createElement("span");
    hint.className = "hint";
    hint.textContent = "未识别到可靠部件,仍可为整件物品生成情景。";
    partsEl.appendChild(hint);
  }
  if (isContainer && !analyzedContents.length) {
    const hint = document.createElement("span");
    hint.className = "hint";
    hint.textContent = "未识别到同时具有描述证据和可靠位置框的内容物。";
    contentsEl.appendChild(hint);
  }

  // Generate for the whole object after Florence context has been stored.
  memoGenerateScenario(obj, null);
}

async function memoGenerateScenario(obj, part) {
  const scenarioToken = ++memo.scenarioToken;
  const scEl = $("memo-scenario"); scEl.replaceChildren();
  setStatus($("memo-scenario-status"), "prep", "正在生成情景对话…");
  try {
    const res = await memoFetch("/memorize/scenario", {
      method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({
        photo_id: memo.photoId,
        object_id: obj.id,
        part_en: part ? part.label_en : "",
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "情景生成失败");
    if (scenarioToken !== memo.scenarioToken) return;
    const speakerStyles = [
      { bg: "var(--primary-soft)", fg: "var(--primary-dark)", border: "var(--primary)" },
      { bg: "var(--accent-soft)", fg: "var(--accent-dark)", border: "var(--accent)" },
      { bg: "var(--purple-soft)", fg: "var(--purple)", border: "var(--purple)" },
      { bg: "var(--amber-soft)", fg: "var(--amber-dark)", border: "var(--fair)" },
    ];
    const speakerStyle = new Map();
    const styleFor = (sp) => {
      if (!speakerStyle.has(sp)) {
        speakerStyle.set(sp, speakerStyles[speakerStyle.size % speakerStyles.length]);
      }
      return speakerStyle.get(sp);
    };
    if (data.scene) {
      const scene = document.createElement("div");
      scene.className = "dialogue-scene";
      scene.textContent = data.scene;
      scEl.appendChild(scene);
    }
    (data.turns || []).forEach((t) => {
      const turn = document.createElement("div");
      turn.className = "dialogue-turn";
      const st = styleFor(t.speaker || "?");
      turn.style.borderLeftColor = st.border;
      const chip = document.createElement("span");
      chip.className = "speaker-chip";
      chip.textContent = t.speaker || "?";
      chip.style.background = st.bg;
      chip.style.color = st.fg;
      chip.style.borderColor = st.border;
      turn.appendChild(chip);
      const en = document.createElement("div");
      en.className = "en";
      en.textContent = t.en;
      turn.appendChild(en);
      if (t.zh) {
        const zh = document.createElement("div");
        zh.className = "zh";
        zh.textContent = t.zh;
        turn.appendChild(zh);
      }
      scEl.appendChild(turn);
    });
    setStatus($("memo-scenario-status"), "", "");
  } catch (e) {
    if (scenarioToken !== memo.scenarioToken) return;
    setStatus($("memo-scenario-status"), "", "情景生成失败:" + e.message);
  }
}

// =====================================================================
// Init
// =====================================================================
async function init() {
  let ready = await checkBackend();
  let attempts = 0;
  while (!ready && attempts < 120) {
    // Frozen backend cold-starts in ~1-3 min every launch (torch/numba/transformers
    // import + model load). Show an explicit "starting" state rather than the
    // misleading "无法连接", and wait long enough to cover slower Macs.
    $("backend-status").textContent = "后端启动中(约 1-3 分钟,正在加载模型)…";
    $("backend-status").className = "status status-pending";
    await new Promise((r) => setTimeout(r, 2000));
    ready = await checkBackend();
    attempts += 1;
  }
  $("record-btn").disabled = false;
  loadVideoList();
  pollWarmup();
  memoWireUpload();
}

init();
