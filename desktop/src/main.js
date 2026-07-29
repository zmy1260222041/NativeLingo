// NativeLingo frontend logic.
// Two modes: audio-upload (original) and video-shadowing (new).
// Talks to the local FastAPI sidecar; backend URL + token injected by the Tauri
// shell, with dev fallbacks.

const BACKEND_URL = window.__NATIVELINGO_BACKEND__ || "http://127.0.0.1:8756";
const BACKEND_TOKEN = window.__NATIVELINGO_TOKEN__ || null;

// boot marker: lets us confirm in the backend log which JS version loaded
fetch(`${BACKEND_URL}/health?boot=v6`).catch(() => {});

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
// Mode switching
// =====================================================================
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("tab-active"));
    tab.classList.add("tab-active");
    const mode = tab.dataset.mode;
    $("mode-video").hidden = mode !== "video";
    $("mode-audio").hidden = mode !== "audio";
    $("results").hidden = true;
  });
});

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
    async start(onStop) {
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
      // timeslice: flush data periodically (WKWebView needs this to emit data)
      rec.start(500);
      this.mediaRecorder = rec;
      this.recording = true;
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
    btn.textContent = "● 开始录音";
    btn.classList.remove("recording");
  } else {
    try {
      await audioRec.start((blob) => {
        audio.learnerBlob = blob;
        const player = $("learner-player");
        player.src = URL.createObjectURL(blob);
        player.hidden = false;
        audioUpdateBtn();
      });
      audioTimer.start();
      btn.textContent = "■ 停止录音";
      btn.classList.add("recording");
    } catch (err) {
      alert("无法访问麦克风: " + err.message);
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
  $("shadow-analyze-status").textContent = msg;
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
      shadowStatus("正在请求麦克风权限…");
      await shadowRec.start((blob) => {
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
      clientLog("getUserMedia succeeded; recording started");
      shadowStatus("跟读中…读完点“停止跟读”");
      shadowTimer.start();
      playShadowClip(); // muted video + subtitles play in sync
      btn.textContent = "■ 停止跟读";
      btn.classList.add("recording");
    } catch (err) {
      clientLog("getUserMedia FAILED: " + (err && err.name) + " / " + (err && err.message));
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
}

init();
