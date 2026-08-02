import "@fontsource-variable/geist/wght.css";
import {
  BACKEND_TOKEN,
  BACKEND_URL,
  apiFetch,
  authHeaders,
  clientLog,
  deadlineFetch,
  installRuntimeLogging,
  readJson,
  tokenQS,
} from "./modules/runtime.js";
import { appStore } from "./modules/state.js";
import { UI_COPY } from "./modules/copy.js";
import { setIconButton } from "./modules/icons.js";
import {
  flipLayout,
  refreshMotion,
  revealHotspots,
  revealImage,
  revealView,
  stackResults,
} from "./modules/motion.js";
import {
  createRecorder,
  makeTimer,
  runCountdown,
  setStatus,
} from "./modules/recording.js";
import { feedbackIndex, formatSpeechRate, scoreColor } from "./modules/results.js";
import { selectedRangeLabel, setSpeakingStage } from "./modules/speaking.js";
import {
  countObjectLabels,
  MEMO_PREPROCESSING_CONTRACT,
  setMemoStage,
} from "./modules/memorizing.js";
import { wireEditorialShell, wireTheme } from "./modules/shell.js";

installRuntimeLogging();

// boot marker: confirms in the backend log which JS build loaded. Fired both at
// load (visible when the backend is already up from a prior session) and again
// once the backend responds, so the marker is reliable across cold starts (the
// load-time ping otherwise fails silently while the backend is still spinning
// up and never reaches the log).
const BOOT_TAG = "v24-editorial";
let _bootMarked = false;
function markBoot() {
  if (_bootMarked) return;
  apiFetch(`/health?boot=${BOOT_TAG}`)
    .then(() => { _bootMarked = true; })
    .catch(() => {});
}
markBoot();

const $ = (id) => document.getElementById(id);

// Memorizing actions should never leave a learner staring at an infinite
// spinner. The backend mirrors this deadline, but AbortController gives the
// UI a prompt, deterministic recovery path even if a local process wedges.
const MEMO_REQUEST_TIMEOUT_MS = 15_000;
const MEMO_HEALTH_TIMEOUT_MS = 3_000;
const MEMO_PRONOUNCE_TIMEOUT_MS = 18_000;
const memoFetch = (path, options = {}, timeoutMs = MEMO_REQUEST_TIMEOUT_MS) =>
  deadlineFetch(path, options, timeoutMs);

// =====================================================================
// Backend health
// =====================================================================
async function checkBackend() {
  const status = $("backend-status");
  try {
    const res = await apiFetch("/health");
    const data = await res.json();
    if (data.status === "ok") {
      status.textContent = data.model_loaded ? UI_COPY.backendReady : "正在载入分析模型";
      status.className = "status status-ok";
      status.dataset.tooltip = status.textContent;
      $("backend-detail").textContent = status.textContent;
      appStore.patch({ backend: { state: "ready", label: status.textContent } });
      markBoot();   // now that the backend is up, the boot marker will reach the log
      return true;
    }
  } catch (_) {}
  status.textContent = UI_COPY.backendUnavailable;
  status.className = "status status-error";
  status.dataset.tooltip = status.textContent;
  $("backend-detail").textContent = status.textContent;
  appStore.patch({ backend: { state: "error", label: status.textContent } });
  return false;
}

// Background prefetch of the heavy analysis models (MMS + phoneme). The backend
// downloads them at startup so the first 分析 isn't a multi-GB blind wait; this
// polls /warmup and surfaces the stage. Polling stops once everything is ready.
let warmupState = null;
const _WARMUP_LABEL = { encoder: "编码器", mms: "MMS 对齐 ~1.2GB", phoneme: "音素 ~2.4GB" };
async function pollWarmup() {
  try {
    warmupState = await (await apiFetch("/warmup")).json();
  } catch (_) { return; }
  if (!warmupState) return;
  const st = $("backend-status");
  if (warmupState.stage === "done") {
    st.textContent = UI_COPY.backendReady;
    st.className = "status status-ok";
    st.dataset.tooltip = st.textContent;
    $("backend-detail").textContent = st.textContent;
    return;
  }
  st.textContent = `正在准备${_WARMUP_LABEL[warmupState.stage] || warmupState.stage}`;
  st.className = "status status-pending";
  st.dataset.tooltip = st.textContent;
  $("backend-detail").textContent = st.textContent;
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
    const panes = document.querySelectorAll(".module-pane");
    flipLayout(panes, () => {
      document.querySelectorAll(".module").forEach((x) => {
        const active = x === mod;
        x.classList.toggle("module-active", active);
        x.setAttribute("aria-pressed", String(active));
      });
      panes.forEach((p) => { p.hidden = p.id !== "module-" + m; });
    });
    if (m !== "speaking") $("results").hidden = true;
    appStore.patch({ module: m });
    revealView($("module-" + m));
    onModuleChange(m);
  });
});

// Speaking sub-tabs (video / audio). Scoped to the Speaking pane so the
// toggle generalizes if more Speaking modes are added later.
document.querySelectorAll("#module-speaking .tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll("#module-speaking .tab").forEach((t) => {
      const active = t === tab;
      t.classList.toggle("tab-active", active);
      t.setAttribute("aria-pressed", String(active));
    });
    const mode = tab.dataset.mode;
    document.querySelectorAll("#module-speaking .mode").forEach((m) => { m.hidden = m.id !== "mode-" + mode; });
    $("results").hidden = true;
    appStore.patch({ speakingMode: mode });
    revealView($("mode-" + mode));
  });
});

// Module lifecycle hook. Memorize warmup/release are wired in Phase D once the
// /memorize/* endpoints + this module's UI exist.
function onModuleChange(module) {
  if (module === "memorize") memoEnter();
  else memoLeave();
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
  setSpeakingStage("source-ready", { mode: "audio", filename: file.name });
  audioUpdateBtn();
});

$("record-btn").addEventListener("click", async () => {
  const btn = $("record-btn");
  if (audioRec.recording) {
    audioRec.stop();
    audioTimer.stop();
    setStatus($("analyze-status"), "", "正在整理录音");
    setIconButton(btn, "record", "开始录音");
    btn.classList.remove("recording");
  } else {
    try {
      const statusEl = $("analyze-status");
      setSpeakingStage("preparing", { mode: "audio" });
      setStatus(statusEl, "prep", "正在准备麦克风");
      btn.disabled = true;
      setIconButton(btn, "record", "正在准备麦克风");
      await audioRec.prepare((blob) => {
        audio.learnerBlob = blob;
        const player = $("learner-player");
        player.src = URL.createObjectURL(blob);
        player.hidden = false;
        audioUpdateBtn();
        setStatus(statusEl, "", "录制完成，可以开始分析");
        setSpeakingStage("recorded", { mode: "audio" });
      });
      setStatus(statusEl, "countdown");
      await runCountdown(statusEl, 3);
      audioRec.begin();
      audioTimer.start();
      setStatus(statusEl, "rec", "正在录音");
      setSpeakingStage("recording", { mode: "audio" });
      btn.disabled = false;
      setIconButton(btn, "stop", "停止录音");
      btn.classList.add("recording");
    } catch (err) {
      btn.disabled = false;
      setIconButton(btn, "record", "开始录音");
      setStatus($("analyze-status"), "", "无法访问麦克风：" + (err.message || err));
      setSpeakingStage("error", { mode: "audio", reason: "microphone" });
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
  statusEl.textContent = "正在分析";
  setSpeakingStage("analyzing", { mode: "audio" });
  const form = new FormData();
  form.append("reference", audio.referenceBlob, "reference");
  form.append("learner", audio.learnerBlob, "learner.webm");
  try {
    const res = await apiFetch("/analyze", {
      method: "POST", body: form, headers: authHeaders(),
    });
    renderResults(await readJson(res, "分析失败"));
    statusEl.textContent = "";
  } catch (err) {
    statusEl.textContent = "分析失败：" + err.message;
    setSpeakingStage("error", { mode: "audio", reason: "analysis" });
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
    const res = await apiFetch("/videos", { headers: authHeaders() });
    const data = await readJson(res, "素材加载失败");
    if (!data.videos || data.videos.length === 0) {
      container.innerHTML = '<div class="empty-inline">暂无视频素材</div>';
      return;
    }
    container.replaceChildren();
    data.videos.forEach((v) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "video-item";
      const name = document.createElement("span");
      name.textContent = v.name;
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = `${v.size_mb} MB`;
      item.append(name, meta);
      item.addEventListener("click", () => selectVideo(v.name, item));
      container.appendChild(item);
    });
  } catch (err) {
    container.textContent = `加载失败：${err.message}`;
    container.classList.add("empty-inline");
  }
}

async function selectVideo(name, itemEl) {
  document.querySelectorAll(".video-item").forEach((el) => el.classList.remove("selected"));
  itemEl.classList.add("selected");
  videoState.name = name;
  videoState.rangeStart = null;
  videoState.rangeEnd = null;
  setSpeakingStage("source-ready", { mode: "video", filename: name });
  $("speaking-empty").hidden = true;

  const sentSection = $("sentence-section");
  const list = $("sentence-list");
  sentSection.hidden = false;
  $("shadow-section").hidden = true;
  list.innerHTML = '<div class="empty-inline">正在准备字幕</div>';
  $("range-info").textContent = "正在转写";
  revealView(sentSection);

  try {
    const res = await apiFetch(`/videos/${encodeURIComponent(name)}/process`, {
      method: "POST", headers: authHeaders(),
    });
    const data = await readJson(res, "转写失败");
    videoState.sentences = data.sentences;
    renderSentences();
  } catch (err) {
    list.textContent = `转写失败：${err.message}`;
    $("range-info").textContent = "无法准备字幕";
    setSpeakingStage("error", { mode: "video", reason: "transcription" });
  }
}

function fmt(t) {
  const m = String(Math.floor(t / 60)).padStart(2, "0");
  const s = String(Math.floor(t % 60)).padStart(2, "0");
  return `${m}:${s}`;
}

function renderSentences() {
  const list = $("sentence-list");
  list.replaceChildren();
  videoState.sentences.forEach((sent) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "sentence-item";
    item.dataset.index = sent.index;
    const index = document.createElement("span");
    index.className = "idx";
    index.textContent = String(sent.index + 1).padStart(2, "0");
    const timestamp = document.createElement("span");
    timestamp.className = "ts";
    timestamp.textContent = fmt(sent.start);
    const text = document.createElement("span");
    text.className = "txt";
    text.textContent = sent.text;
    item.append(index, timestamp, text);
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
    setSpeakingStage("range-started", { start: idx });
  } else {
    // set the end
    st.rangeEnd = idx;
    if (st.rangeEnd < st.rangeStart) {
      [st.rangeStart, st.rangeEnd] = [st.rangeEnd, st.rangeStart];
    }
    setSpeakingStage("range-ready", { start: st.rangeStart, end: st.rangeEnd });
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
    info.textContent = "点按一句开始";
    $("shadow-section").hidden = true;
    return;
  }
  const s = st.sentences[start];
  const e = st.sentences[end];
  info.textContent = selectedRangeLabel(start, st.rangeEnd);

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
  revealView($("shadow-section"));
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
    setIconButton(btn, "record", "开始跟读");
    btn.classList.remove("recording");
    shadowStatus("正在整理录音");
  } else {
    if (videoState.rangeStart === null) {
      shadowStatus("请先选择要跟读的句子");
      return;
    }
    clientLog("mediaDevices exists=" + !!(navigator.mediaDevices) +
      " getUserMedia=" + !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia));
    try {
      const statusEl = $("shadow-analyze-status");
      setSpeakingStage("preparing", { mode: "video" });
      setStatus(statusEl, "prep", "正在准备麦克风");
      btn.disabled = true;
      setIconButton(btn, "record", "正在准备麦克风");
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
        shadowStatus(blob.size > 0 ? "录制完成，可以开始分析" : "没有录到声音，请重试");
        setSpeakingStage(blob.size > 0 ? "recorded" : "error", { mode: "video" });
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
      setStatus(statusEl, "rec", "正在录音");
      setSpeakingStage("recording", { mode: "video" });
      btn.disabled = false;
      setIconButton(btn, "stop", "停止跟读");
      btn.classList.add("recording");
    } catch (err) {
      clientLog("getUserMedia FAILED: " + (err && err.name) + " / " + (err && err.message));
      btn.disabled = false;
      setIconButton(btn, "record", "开始跟读");
      shadowStatus("无法访问麦克风：" + (err && err.message ? err.message : err));
      setSpeakingStage("error", { mode: "video", reason: "microphone" });
    }
  }
});

$("shadow-analyze-btn").addEventListener("click", async () => {
  const statusEl = $("shadow-analyze-status");
  const btn = $("shadow-analyze-btn");
  btn.disabled = true;
  setSpeakingStage("analyzing", { mode: "video" });
  statusEl.textContent = (warmupState && warmupState.stage !== "done")
    ? "正在准备分析模型"
    : "正在分析";
  const st = videoState;
  const end = st.rangeEnd !== null ? st.rangeEnd : st.rangeStart;
  const form = new FormData();
  form.append("video", st.name);
  form.append("start_index", st.rangeStart);
  form.append("end_index", end);
  form.append("learner", st.learnerBlob, "learner.webm");
  try {
    const res = await apiFetch("/analyze_video", {
      method: "POST", body: form, headers: authHeaders(),
    });
    renderResults(await readJson(res, "分析失败"));
    statusEl.textContent = "";
  } catch (err) {
    statusEl.textContent = "分析失败：" + err.message;
    setSpeakingStage("error", { mode: "video", reason: "analysis" });
  } finally {
    btn.disabled = false;
  }
});

// =====================================================================
// Shared results rendering
// =====================================================================
function renderResults(data) {
  $("results").hidden = false;
  setSpeakingStage("results", { score: Math.round(data.overall_score) });

  const refText = $("reference-text");
  if (data.reference_text) {
    refText.textContent = "参考文本：" + data.reference_text;
    refText.hidden = false;
  } else {
    refText.hidden = true;
  }

  const set = (id, val) => {
    const el = $(id);
    el.textContent = Math.round(val);
    const track = id === "accuracy-score" ? $("accuracy-track") : id === "fluency-score" ? $("fluency-track") : null;
    if (track) {
      track.style.setProperty("--score", `${Math.max(0, Math.min(100, val))}%`);
      track.style.setProperty("--score-color", scoreColor(val));
    }
  };
  set("overall-score", data.overall_score);
  set("accuracy-score", data.accuracy);
  set("fluency-score", data.fluency);

  $("rate-info").textContent = formatSpeechRate(data.speech_rate_ratio);

  const tipsList = $("tips-list");
  tipsList.innerHTML = "";
  (data.tips || []).forEach((tip) => {
    const li = document.createElement("li");
    li.textContent = tip;
    tipsList.appendChild(li);
  });
  if (!(data.tips || []).length) {
    const li = document.createElement("li");
    li.className = "tips-empty";
    li.textContent = "本次没有明显的改进点，继续保持当前发音。";
    tipsList.appendChild(li);
  }

  const prosody = data.prosody;
  if (prosody) {
    const prosodyInfo = $("prosody-info");
    prosodyInfo.replaceChildren();
    [
      `语调 ${Math.round(prosody.intonation_match)}`,
      `停顿 ${Math.round(prosody.pause_match)}`,
      `停顿次数 ${prosody.learner_pauses}，参考 ${prosody.reference_pauses}`,
    ].forEach((text) => {
      const item = document.createElement("span");
      item.textContent = text;
      prosodyInfo.appendChild(item);
    });
  }

  renderSentenceDetails(data.sentences, data.segment);
  revealView($("results"));
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
  container.replaceChildren();

  // point the learner clip player at the current recording (if any)
  const myPlayer = $("my-clip-player");
  if (myPlayer && videoState.learnerUrl && myPlayer.src !== videoState.learnerUrl) {
    myPlayer.src = videoState.learnerUrl;
  }

  sentences.forEach((sd, sentenceIndex) => {
    const card = document.createElement("div");
    card.className = "sent-detail";
    card.style.setProperty("--stack-offset", `${Math.min(sentenceIndex, 5) * 6}px`);

    const head = document.createElement("div");
    head.className = "sent-head";
    const scores = document.createElement("span");
    scores.className = "sent-scores";
    const accuracy = document.createElement("span");
    accuracy.textContent = `准确度 ${Math.round(sd.accuracy)}`;
    accuracy.style.color = scoreColor(sd.accuracy);
    const fluency = document.createElement("span");
    fluency.textContent = `流畅度 ${Math.round(sd.fluency)}`;
    fluency.style.color = scoreColor(sd.fluency);
    scores.append(accuracy, fluency);
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
      refBtn.type = "button";
      setIconButton(refBtn, "play", "播放原声");
      refBtn.addEventListener("click", () => playRefClip(absStart, absEnd));
      btns.appendChild(refBtn);
    }
    if (videoState.learnerUrl && sd.learner_end > sd.learner_start) {
      const myBtn = document.createElement("button");
      myBtn.className = "sent-play sent-play-mine";
      myBtn.type = "button";
      setIconButton(myBtn, "audio", "播放我的录音");
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
      tipsEl.className = "word-tips feedback-carousel";
      const feedbackViewport = document.createElement("div");
      feedbackViewport.className = "feedback-viewport";
      const feedbackControls = document.createElement("div");
      feedbackControls.className = "feedback-controls";
      const previous = document.createElement("button");
      previous.type = "button";
      previous.className = "icon-button compact";
      setIconButton(previous, "chevronLeft", "上一条反馈");
      const counter = document.createElement("span");
      const next = document.createElement("button");
      next.type = "button";
      next.className = "icon-button compact";
      setIconButton(next, "chevronRight", "下一条反馈");
      const rows = [];
      tipped.forEach((w, tipIndex) => {
        const row = document.createElement("div");
        row.className = "word-tip";
        row.hidden = tipIndex !== 0;

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
          rb.type = "button";
          setIconButton(rb, "play", `播放 ${w.word} 的原声`);
          rb.addEventListener("click", () =>
            playRefClip(segment.start + w.start, segment.start + w.end));
          ab.appendChild(rb);
        }
        if (videoState.learnerUrl && w.learner_end > w.learner_start) {
          const mb = document.createElement("button");
          mb.className = "wt-btn wt-btn-mine";
          mb.type = "button";
          setIconButton(mb, "audio", `播放我读的 ${w.word}`);
          mb.addEventListener("click", () => playMyClip(w.learner_start, w.learner_end));
          ab.appendChild(mb);
        }
        row.appendChild(ab);
        rows.push(row);
        feedbackViewport.appendChild(row);
      });
      let activeTip = 0;
      const showTip = (index) => {
        activeTip = feedbackIndex(0, index, rows.length);
        rows.forEach((row, rowIndex) => { row.hidden = rowIndex !== activeTip; });
        counter.textContent = `${activeTip + 1} / ${rows.length}`;
        revealView(rows[activeTip]);
      };
      previous.addEventListener("click", () => showTip(activeTip - 1));
      next.addEventListener("click", () => showTip(activeTip + 1));
      feedbackControls.append(previous, counter, next);
      tipsEl.append(feedbackViewport);
      if (rows.length > 1) tipsEl.append(feedbackControls);
      showTip(0);
      card.appendChild(tipsEl);
    }
    container.appendChild(card);
  });
  stackResults(container);
  refreshMotion();
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
    const res = await apiFetch("/recordings", {
      method: "POST", body: form, headers: authHeaders(),
    });
    const data = await readJson(res, "无法保存录音");
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
// (FR-15). All recognition is on-device (NFR-5). Decodable image files are
// uploaded unchanged: the backend owns EXIF correction, resize and JPEG
// canonicalization so production and tests see identical model pixels. Canvas
// is only a format/oversize adapter (for example HEIC), never the model-input
// specification.
const memo = {
  entered: false,
  warmupTimer: null,
  imgEl: null,
  imgW: 0, imgH: 0,        // authoritative backend-canonical pixel dimensions
  previewUrl: null,
  photoId: null,
  objects: [],
  recognitionToken: 0,
  detailToken: 0,
  scenarioToken: 0,
  pronounceToken: 0,
  pronounceWord: "",       // FR-17: word/phrase currently targeted for practice
  pronounceRecorder: null,
};
const MEMO_MAX_DIM = 1920;
const MEMO_MAX_DIRECT_UPLOAD_BYTES = 50_000_000;
const MEMO_BACKEND_IMAGE_TYPES = new Set([
  "image/jpeg", "image/png", "image/webp",
]);
const _MEMO_STAGE_LABEL = {
  yolo: "YOLO 检测模型",
  llm: "Qwen Q4_K_M 情景模型 ~491MB",
  florence: "Florence 视觉增强模型 ~463MB",
  piper: "Piper 发音模型 ~63MB",
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
      memoStatus("err", "模型准备失败：" + (st.error || "请稍后重试"));
    } else if (busy) {
      memoStatus("", `正在准备${_MEMO_STAGE_LABEL[st.stage] || st.stage}`);
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
    memoPronounceReset();
    $("memo-detail").hidden = true;
    appStore.patch({ memoView: "recognition" });
    setMemoStage("photo", { objects: memo.objects.length });
    $("memo-view").scrollIntoView({ behavior: "smooth" });
  });
}

function memoResetToUpload() {
  memoPronounceReset();
  $("memo-view").hidden = true;
  $("memo-detail").hidden = true;
  $("memo-upload").closest(".card").hidden = false;
  memo.objects = []; memo.photoId = null;
  memo.recognitionToken += 1;
  memo.detailToken += 1;
  memo.scenarioToken += 1;
  if (memo.previewUrl) URL.revokeObjectURL(memo.previewUrl);
  memo.previewUrl = null;
  $("memo-hotspots").innerHTML = "";
  $("memo-object-summary").hidden = true;
  $("memo-object-summary").textContent = "";
  appStore.patch({ memoView: "upload" });
  setMemoStage("upload");
  revealView($("memo-upload").closest(".card"));
}

function memoLoadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const im = new Image();
    im.onload = () => {
      URL.revokeObjectURL(url);
      resolve(im);
    };
    im.onerror = () => { URL.revokeObjectURL(url); reject(new Error("decode")); };
    im.src = url;
  });
}

function memoBackendCanDecode(file) {
  const type = String(file.type || "").toLowerCase();
  const name = String(file.name || "").toLowerCase();
  return MEMO_BACKEND_IMAGE_TYPES.has(type) || /\.(jpe?g|png|webp)$/.test(name);
}

// Keep ordinary photos byte-for-byte intact until the backend canonicalizer.
// Canvas is only used when Pillow cannot decode the format or the original is
// above the local upload cap. Its output still goes through the same backend
// canonicalizer before detection.
async function memoPrepareUpload(file) {
  const im = await memoLoadImage(file);
  if (file.size <= MEMO_MAX_DIRECT_UPLOAD_BYTES && memoBackendCanDecode(file)) {
    return {
      blob: file,
      previewBlob: file,
      filename: file.name || "photo",
      transport: "original",
      w: im.naturalWidth,
      h: im.naturalHeight,
    };
  }

  let w = im.naturalWidth, h = im.naturalHeight;
  const scale = Math.min(1, MEMO_MAX_DIM / Math.max(w, h));
  w = Math.max(1, Math.round(w * scale));
  h = Math.max(1, Math.round(h * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const context = canvas.getContext("2d");
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(im, 0, 0, w, h);
  const blob = await new Promise((resolve, reject) => {
    canvas.toBlob(
      (value) => (value ? resolve(value) : reject(new Error("encode"))),
      "image/jpeg",
      0.9,
    );
  });
  return {
    blob,
    previewBlob: blob,
    filename: "photo.jpg",
    transport: "browser-adapter",
    w,
    h,
  };
}

async function memoHandleFile(file) {
  const recognitionToken = ++memo.recognitionToken;
  let enc;
  try { enc = await memoPrepareUpload(file); }
  catch (e) {
    memoStatus("err", "无法读取图片，请换一张常见格式的照片。");
    setMemoStage("error", { reason: "decode" });
    return;
  }

  $("memo-upload").closest(".card").hidden = true;
  $("memo-detail").hidden = true;
  const view = $("memo-view"); view.hidden = false;
  appStore.patch({ memoView: "recognition" });
  setMemoStage("analyzing", { filename: file.name });
  revealView(view);
  const img = $("memo-img");
  if (memo.previewUrl) URL.revokeObjectURL(memo.previewUrl);
  memo.previewUrl = URL.createObjectURL(enc.previewBlob);
  img.src = memo.previewUrl;
  img.addEventListener("load", () => revealImage(img), { once: true });
  memo.imgEl = img;
  memo.imgW = enc.w; memo.imgH = enc.h;
  $("memo-hotspots").innerHTML = "";
  $("memo-object-summary").hidden = true;
  $("memo-object-summary").textContent = "";
  $("memo-analyzing").hidden = false;

  try {
    const form = new FormData();
    form.append("photo", enc.blob, enc.filename);
    clientLog(`memorize photo transport=${enc.transport} bytes=${enc.blob.size}`);
    const res = await memoFetch("/memorize/analyze", {
      method: "POST", body: form, headers: authHeaders(),
    });
    const data = await readJson(res, "识别失败");
    if (data.preprocessing !== MEMO_PREPROCESSING_CONTRACT) {
      throw new Error("后端图像预处理版本不匹配，请重新打开应用。");
    }
    if (recognitionToken !== memo.recognitionToken) return;
    memo.photoId = data.photo_id;
    if (Array.isArray(data.image_size) && data.image_size.length === 2 &&
        data.image_size.every((value) => Number.isFinite(Number(value)) && Number(value) > 0)) {
      memo.imgW = Number(data.image_size[0]);
      memo.imgH = Number(data.image_size[1]);
    }
    memo.objects = data.objects || [];
    memoRenderHotspots();
    setMemoStage("photo", { objects: memo.objects.length });
  } catch (e) {
    if (recognitionToken !== memo.recognitionToken) return;
    memoStatus("err", `识别失败：${e.message} 请重试或换张照片。`);
    setMemoStage("error", { reason: "recognition" });
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
  const counts = countObjectLabels(memo.objects);
  summary.replaceChildren();
  summary.classList.remove("is-overflowing");
  const ribbon = document.createElement("div");
  ribbon.className = "object-ribbon";
  [...counts.entries()].forEach(([label, count]) => {
    const word = document.createElement("button");
    word.type = "button";
    word.className = "object-word";
    word.textContent = `${label}${count > 1 ? ` ×${count}` : ""}`;
    word.addEventListener("click", () => {
      const object = memo.objects.find((item) => item.label_en === label);
      if (object) memoOpenDetail(object);
    });
    ribbon.appendChild(word);
  });
  summary.appendChild(ribbon);
  summary.hidden = false;
  window.requestAnimationFrame(() => {
    if (ribbon.scrollWidth <= summary.clientWidth) return;
    [...ribbon.children].forEach((word) => {
      const clone = word.cloneNode(true);
      clone.setAttribute("aria-hidden", "true");
      clone.tabIndex = -1;
      ribbon.appendChild(clone);
    });
    summary.classList.add("is-overflowing");
  });

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
    // Hotspots are clickable overlays; make them keyboard-accessible like the
    // part buttons (Tab to focus, Enter/Space to open the object detail).
    dot.tabIndex = 0;
    dot.setAttribute("role", "button");
    dot.setAttribute("aria-label", `查看物品 ${o.label_en}`);
    dot.addEventListener("click", () => memoOpenDetail(o));
    dot.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        memoOpenDetail(o);
      }
    });
    hs.appendChild(dot);
  });
  revealHotspots(hs);
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
  const sourceScaleX = memo.imgEl.naturalWidth / Math.max(1, memo.imgW);
  const sourceScaleY = memo.imgEl.naturalHeight / Math.max(1, memo.imgH);
  canvas.getContext("2d").drawImage(
    memo.imgEl,
    x * sourceScaleX,
    y * sourceScaleY,
    w * sourceScaleX,
    h * sourceScaleY,
    0,
    0,
    canvas.width,
    canvas.height,
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
  memoPronounceReset();            // FR-17: clear previous scores/recording
  memo.pronounceWord = obj.label_en;
  memoPronounceHint(obj.label_en);
  $("memo-pronounce-record").disabled = false;
  const detail = $("memo-detail");
  detail.hidden = false;
  appStore.patch({ memoView: "detail" });
  setMemoStage("detail", { object: obj.label_en });
  revealView(detail);
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
    const data = await readJson(res, "部件识别失败");
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
    setStatus($("memo-parts-status"), "", `部件识别失败：${e.message} 请重试。`);
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
    memo.pronounceWord = part.label_en;   // FR-17: practice follows the selection
    memoPronounceHint(part.label_en);
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
    const wrapper = document.createElement("span");
    wrapper.className = "part-chip-wrap";
    wrapper.appendChild(chip);
    const playBtn = document.createElement("button");
    playBtn.type = "button";
    playBtn.className = "pronounce-play-btn";
    setIconButton(playBtn, "play", `播放 ${part.label_en} 的标准发音`);
    playBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      memoPronouncePlay(part.label_en);
    });
    wrapper.appendChild(playBtn);
    parent.appendChild(wrapper);
    chipByPart.set(part, chip);
  };
  const whole = {
    label_en: obj.label_en,
    label_zh: obj.label_zh,
    whole: true,
    kind: "whole",
  };
  addChip(whole, partsEl, obj.label_en, true);
  analyzedParts.forEach((part) => addChip(part, partsEl, part.label_en));
  analyzedContents.forEach((item) => addChip(item, contentsEl, item.label_en));

  hotspotByPart = memoRenderPartHotspots(
    [...analyzedContents, ...analyzedParts],
    detailCropSize,
    selectPart,
    chipByPart,
  );
  revealImage($("memo-detail-img"));
  revealHotspots($("memo-part-hotspots"));
  setStatus($("memo-parts-status"), "", "");
  if (!analyzedParts.length) {
    const hint = document.createElement("span");
    hint.className = "empty-inline";
    hint.textContent = "没有找到可靠部件，仍可使用整件物品练习。";
    partsEl.appendChild(hint);
  }
  if (isContainer && !analyzedContents.length) {
    const hint = document.createElement("span");
    hint.className = "empty-inline";
    hint.textContent = "没有找到位置可靠的内容物。";
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
    const data = await readJson(res, "情景生成失败");
    if (scenarioToken !== memo.scenarioToken) return;
    if (data.scene) {
      const scene = document.createElement("div");
      scene.className = "dialogue-scene";
      scene.textContent = data.scene;
      scEl.appendChild(scene);
    }
    (data.turns || []).forEach((t) => {
      const turn = document.createElement("div");
      turn.className = "dialogue-turn";
      const chip = document.createElement("span");
      chip.className = "speaker-chip";
      chip.textContent = t.speaker || "?";
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
    setStatus($("memo-scenario-status"), "", `情景生成失败：${e.message} 请重试。`);
    setMemoStage("error", { reason: "scenario" });
  }
}

// ---- FR-17: word pronunciation (playback + optional shadow score) ----
const memoPronounceRecorder = createRecorder();
const memoPronounceTimer = makeTimer("memo-pronounce-timer");
let memoPronounceAudioUrl = "";
let memoPronouncePlayToken = 0;

function memoPronounceClearAudio() {
  const player = $("memo-pronounce-player");
  if (player) {
    player.pause();
    player.removeAttribute("src");
    player.load();
  }
  if (memoPronounceAudioUrl) {
    URL.revokeObjectURL(memoPronounceAudioUrl);
    memoPronounceAudioUrl = "";
  }
}

async function memoPronouncePlay(text) {
  if (!text) return;
  const playToken = ++memoPronouncePlayToken;
  const tok = BACKEND_TOKEN ? `&token=${encodeURIComponent(BACKEND_TOKEN)}` : "";
  const path = `/memorize/tts?text=${encodeURIComponent(text)}${tok}`;
  try {
    // Fetch once so backend errors remain readable, then play that same
    // response. Assigning the endpoint to player.src would issue a second TTS
    // request and synthesize the same word again.
    const response = await apiFetch(path);
    if (!response.ok) {
      let detail = "HTTP " + response.status;
      try {
        const data = await response.json();
        if (data && data.detail) detail = data.detail;
      } catch (_) {
        // Keep the HTTP status when the error response is not JSON.
      }
      throw new Error(detail);
    }
    const blob = await response.blob();
    if (playToken !== memoPronouncePlayToken) return;
    if (!blob.size) throw new Error("语音合成返回了空音频");

    memoPronounceClearAudio();
    const player = $("memo-pronounce-player");
    memoPronounceAudioUrl = URL.createObjectURL(blob);
    player.src = memoPronounceAudioUrl;
    await player.play();
  } catch (e) {
    if (playToken !== memoPronouncePlayToken) return;
    setStatus($("memo-parts-status"), "", "发音加载失败：" + (e && e.message));
    clientLog("pronounce play failed: " + (e && e.message));
  }
}

function memoPronounceHint(text) {
  const hint = $("memo-pronounce-hint");
  if (hint) {
    hint.textContent = text || "选择一个词开始跟读";
  }
}

function memoPronounceReset() {
  memoPronouncePlayToken += 1;
  memo.pronounceToken += 1;
  if (memoPronounceRecorder.recording) memoPronounceRecorder.stop();
  memoPronounceTimer.stop();
  const btn = $("memo-pronounce-record");
  if (btn) {
    setIconButton(btn, "record", "开始录音");
    btn.classList.remove("recording");
  }
  const score = $("memo-pronounce-score");
  if (score) { score.hidden = true; score.replaceChildren(); }
  memoPronounceClearAudio();
}

function memoPronounceScoreBadge(label, value) {
  const cls = value >= 75 ? "good" : value >= 60 ? "weak" : "bad";
  return `<div class="score-badge ${cls}"><div class="score-label">${label}</div>` +
         `<div class="score-value">${value.toFixed(0)}</div></div>`;
}

async function memoPronounceSubmit(blob) {
  const token = ++memo.pronounceToken;
  const word = memo.pronounceWord;
  const btn = $("memo-pronounce-record");
  const scoreEl = $("memo-pronounce-score");
  btn.disabled = true;
  setIconButton(btn, "record", "正在检查评分服务");
  scoreEl.hidden = false;
  scoreEl.innerHTML = `<p class="score-note">正在检查评分服务</p>`;
  try {
    const healthRes = await memoFetch(
      "/memorize/pronounce/status",
      {},
      MEMO_HEALTH_TIMEOUT_MS,
    );
    const health = await healthRes.json().catch(() => ({}));
    if (!healthRes.ok || health.status !== "ok") {
      throw new Error(health.detail || "本地评分服务未就绪");
    }
    if (token !== memo.pronounceToken) return;

    setIconButton(btn, "record", "正在评分");
    scoreEl.innerHTML = health.ready
      ? `<p class="score-note">正在对比参考音</p>`
      : `<p class="score-note">评分模型正在准备</p>`;
    const form = new FormData();
    form.append("text", word);
    form.append("learner", blob, "learner.webm");
    const res = await memoFetch(
      "/memorize/pronounce",
      { method: "POST", body: form },
      MEMO_PRONOUNCE_TIMEOUT_MS,
    );
    const data = await readJson(res, "发音评分失败");
    if (token !== memo.pronounceToken) return;
    scoreEl.innerHTML =
      `<div class="score-row">` +
      memoPronounceScoreBadge("准确度", data.accuracy) +
      memoPronounceScoreBadge("流畅度", data.fluency) +
      `</div>` +
      `<p class="score-note">本地声学对比结果</p>`;
  } catch (e) {
    if (token !== memo.pronounceToken) return;
    scoreEl.replaceChildren();
    const error = document.createElement("p");
    error.className = "score-note error";
    error.textContent = `评分失败：${e.message}`;
    scoreEl.appendChild(error);
  } finally {
    if (token === memo.pronounceToken) {
      btn.disabled = false;
      setIconButton(btn, "record", "重新录音");
    }
  }
}

function memoPronounceToggleRecord() {
  const btn = $("memo-pronounce-record");
  const timer = $("memo-pronounce-timer");
  const onStop = (blob) => {
    if (!blob || blob.size === 0) {
      btn.disabled = false;
      setIconButton(btn, "record", "重新录音");
      const scoreEl = $("memo-pronounce-score");
      scoreEl.hidden = false;
      scoreEl.innerHTML = `<p class="score-note error">没有录到声音，请检查麦克风后重试。</p>`;
      clientLog("pronounce: empty recording");
      return;
    }
    const player = $("memo-pronounce-player");
    memoPronounceClearAudio();
    memoPronounceAudioUrl = URL.createObjectURL(blob);
    player.src = memoPronounceAudioUrl;
    player.hidden = false;
    memoPronounceSubmit(blob);
  };
  if (memoPronounceRecorder.recording) {
    memoPronounceRecorder.stop();
    memoPronounceTimer.stop();
    btn.disabled = true;
    setIconButton(btn, "record", "正在整理录音");
    btn.classList.remove("recording");
  } else {
    setMemoStage("practicing", { word: memo.pronounceWord });
    memoPronounceRecorder.prepare(onStop).then(() => {
      memoPronounceRecorder.begin();
      memoPronounceTimer.start();
      setIconButton(btn, "stop", "停止录音");
      btn.classList.add("recording");
    }).catch((err) => {
      memoPronounceHint("无法访问麦克风：" + (err && err.message ? err.message : err));
    });
  }
  if (timer) timer.style.display = "inline";
}

$("memo-pronounce-record").addEventListener("click", memoPronounceToggleRecord);

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
    $("backend-status").textContent = UI_COPY.backendStarting;
    $("backend-status").className = "status status-pending";
    $("backend-status").dataset.tooltip = UI_COPY.backendStarting;
    $("backend-detail").textContent = UI_COPY.backendStarting;
    await new Promise((r) => setTimeout(r, 2000));
    ready = await checkBackend();
    attempts += 1;
  }
  $("record-btn").disabled = false;
  loadVideoList();
  pollWarmup();
  memoWireUpload();
}

wireEditorialShell();
wireTheme();
init();
