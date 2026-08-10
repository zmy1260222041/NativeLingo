// Capture page logic for the R-14 G1/G2 corpus. Review tool, not product code.
//
// The recorder below is a verbatim port of the MediaRecorder path in
// desktop/src/modules/recording.js -- same pickMime() candidate order, same
// bare getUserMedia({audio:true}) with no constraint overrides, same
// start(500) timeslice, same requestData() -> stop() -> 800ms _finalize()
// fallback. That fallback exists because WKWebView does not always fire onstop.
//
// Why copy rather than import: importing from ../../desktop/src/ would make a
// review script a consumer of product code, and the module pulls in
// runtime.js (bearer-token apiFetch) which has no meaning here. The port is
// small and the divergence risk is stated in the README.
//
// Why mirror it at all: the ASR spec (scripts/fixtures/game_asr/README.md §3)
// requires capture through the production path. An external recorder yields
// audio slightly *better* than production, and that bias direction makes G2
// systematically optimistic -- an optimistic gate is worse than an unmeasured
// one, because it looks measured.
//
// This file never requests or renders slots.accept or reference_answer. The
// server does not send them (serve.py::_strip whitelists six fields), so there
// is nothing to leak even by accident.

const PROBE_PLAN = { infant: 10, toddler: 10 };

function pickMime() {
  const candidates = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", ""];
  for (const candidate of candidates) {
    if (!candidate || (window.MediaRecorder && MediaRecorder.isTypeSupported(candidate))) {
      return candidate;
    }
  }
  return "";
}

function extFor(mime) {
  if (!mime) return ".m4a";
  if (mime.includes("mp4")) return ".m4a";
  if (mime.includes("webm")) return ".webm";
  if (mime.includes("ogg")) return ".ogg";
  return ".bin";
}

function createRecorder() {
  return {
    mediaRecorder: null,
    chunks: [],
    recording: false,
    blob: null,
    stream: null,
    _onStop: null,
    _finalized: false,
    _finalize() {
      if (this._finalized) return;
      this._finalized = true;
      const type = this.mediaRecorder?.mimeType || "audio/mp4";
      this.blob = new Blob(this.chunks, { type });
      this.stream?.getTracks().forEach((track) => track.stop());
      this._onStop?.(this.blob);
    },
    async start(onStop) {
      this._onStop = onStop;
      this._finalized = false;
      this.blob = null;
      // No constraint overrides: echoCancellation / noiseSuppression /
      // autoGainControl are left at browser defaults exactly as the app leaves
      // them. Turning them off here would make the corpus cleaner than
      // production audio, which is the bias this whole page exists to avoid.
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.chunks = [];
      const mime = pickMime();
      const recorder = mime
        ? new MediaRecorder(this.stream, { mimeType: mime })
        : new MediaRecorder(this.stream);
      recorder.ondataavailable = (event) => {
        if (event.data?.size) this.chunks.push(event.data);
      };
      recorder.onstop = () => this._finalize();
      recorder.onerror = (event) => {
        setStatus(`录音出错: ${event.error?.name || "unknown"}`);
      };
      this.mediaRecorder = recorder;
      recorder.start(500);
      this.recording = true;
    },
    stop() {
      if (!this.mediaRecorder || !this.recording) return;
      this.recording = false;
      try {
        this.mediaRecorder.requestData();
      } catch (_) {}
      try {
        this.mediaRecorder.stop();
      } catch (_) {}
      window.setTimeout(() => this._finalize(), 800);
    },
  };
}

const el = (id) => document.getElementById(id);
const setStatus = (text) => {
  el("status").textContent = text;
};

const state = {
  speaker: "",
  l1: "",
  queue: [],
  index: 0,
  recorder: null,
  pending: null, // { blob, url, clip, scenario, tier, mime, duration_s }
  saved: [],
  startedAt: 0,
};

function shuffle(items, seed) {
  // Deterministic per speaker code: reloading after a crash keeps the same
  // order, so a partially-finished session resumes on the same scenario list.
  const out = items.slice();
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) % 2147483647;
  let rng = h || 1;
  for (let i = out.length - 1; i > 0; i -= 1) {
    rng = (rng * 48271) % 2147483647;
    const j = rng % (i + 1);
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function planFromQuery() {
  const raw = new URLSearchParams(location.search).get("tiers");
  if (!raw) return { ...PROBE_PLAN };
  const plan = {};
  for (const part of raw.split(",")) {
    const [tier, count] = part.split(":");
    const n = Number.parseInt(count, 10);
    if (tier && Number.isFinite(n) && n > 0) plan[tier.trim()] = n;
  }
  return Object.keys(plan).length ? plan : { ...PROBE_PLAN };
}

function buildQueue(scenarios, plan, seed) {
  const queue = [];
  for (const [tier, wanted] of Object.entries(plan)) {
    const pool = shuffle(
      scenarios.filter((s) => s.tier === tier),
      `${seed}:${tier}`,
    );
    if (!pool.length) continue;
    // Round-robin over the tier's scenarios rather than taking the first N.
    // Both READMEs ask that no single scenario's accept set dominate a tier's
    // number; with 10 clips over 8 infant scenarios that means 2 scenarios get
    // a second clip, not 1 scenario getting 3.
    for (let i = 0; i < wanted; i += 1) queue.push(pool[i % pool.length]);
  }
  return queue;
}

async function loadScenarios() {
  const res = await fetch("./scenarios.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`scenarios.json ${res.status}`);
  return res.json();
}

function renderCurrent() {
  const item = state.queue[state.index];
  el("progress").textContent = `${state.index + 1} / ${state.queue.length}`;
  el("tier").textContent = item.tier;
  el("need").textContent = `${item.need} · L${item.maslow_level}`;
  el("situation").textContent = item.situation_zh;
  el("greeting").textContent = item.greeting;
  el("rec").textContent = "开始录音";
  el("rec").disabled = false;
  el("replay").disabled = true;
  el("redo").disabled = true;
  el("next").disabled = true;
  el("player").hidden = true;
  setStatus("用英语说出你的意图 —— 想到什么说什么,不用组织完整句子,说错也不要重录。");
}

function discardPending() {
  if (state.pending?.url) URL.revokeObjectURL(state.pending.url);
  state.pending = null;
}

async function toggleRecord() {
  const button = el("rec");
  if (state.recorder?.recording) {
    button.disabled = true;
    setStatus("处理中…");
    state.recorder.stop();
    return;
  }
  discardPending();
  state.recorder = createRecorder();
  const item = state.queue[state.index];
  const seq = String(state.index + 1).padStart(2, "0");
  try {
    state.startedAt = performance.now();
    await state.recorder.start((blob) => onRecorded(blob, item, seq));
  } catch (err) {
    setStatus(`拿不到麦克风: ${err?.message || err}`);
    return;
  }
  button.textContent = "停止录音";
  setStatus("录音中… 说完点「停止录音」");
}

function onRecorded(blob, item, seq) {
  const duration = (performance.now() - state.startedAt) / 1000;
  const mime = blob.type || "";
  const clip = `${item.tier}-${item.id}-${state.speaker}-${seq}${extFor(mime)}`;
  state.pending = {
    blob,
    url: URL.createObjectURL(blob),
    clip,
    scenario: item.id,
    tier: item.tier,
    mime,
    duration_s: Number(duration.toFixed(2)),
  };
  const player = el("player");
  player.src = state.pending.url;
  player.hidden = false;
  el("rec").textContent = "开始录音";
  el("rec").disabled = true;
  el("replay").disabled = false;
  el("redo").disabled = false;
  el("next").disabled = false;
  const kb = (blob.size / 1024).toFixed(0);
  let note = `已录 ${duration.toFixed(1)}s · ${kb} KB · ${mime || "默认容器"}`;
  if (duration < 0.8) note += " —— 偏短,确认说完整了";
  if (duration > 8) note += " —— 偏长,规格是 1–6s";
  setStatus(note);
}

async function saveAndAdvance() {
  const pending = state.pending;
  if (!pending) return;
  el("next").disabled = true;
  setStatus("保存中…");
  try {
    const res = await fetch(`./clip/${encodeURIComponent(pending.clip)}`, {
      method: "POST",
      headers: { "Content-Type": pending.mime || "application/octet-stream" },
      body: pending.blob,
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`${res.status} ${detail}`);
    }
    const info = await res.json();
    state.saved.push({
      clip: info.clip,
      scenario: pending.scenario,
      tier: pending.tier,
      speaker: state.speaker,
      l1: state.l1,
      mime: pending.mime,
      duration_s: pending.duration_s,
      recorded_at: new Date().toISOString(),
      capture_page: "scripts/collect",
    });
  } catch (err) {
    el("next").disabled = false;
    setStatus(`保存失败,没有前进: ${err?.message || err}`);
    return;
  }
  discardPending();
  state.index += 1;
  if (state.index >= state.queue.length) return finish();
  renderCurrent();
}

function finish() {
  el("stage").hidden = true;
  el("done").hidden = false;
  const tiers = {};
  const scenarios = new Set();
  for (const row of state.saved) {
    tiers[row.tier] = (tiers[row.tier] || 0) + 1;
    scenarios.add(row.scenario);
  }
  el("doneSummary").textContent =
    `本轮 ${state.saved.length} 条,覆盖 ${scenarios.size} 个场景。` +
    `点导出把 manifest / CSV 骨架写到 scripts/fixtures/game_asr/。`;
  const rows = Object.entries(tiers)
    .map(([tier, n]) => `<tr><td>${tier}</td><td>${n}</td></tr>`)
    .join("");
  el("tally").innerHTML = `<tr><th>tier</th><th>条数</th></tr>${rows}`;
}

async function exportManifest() {
  const button = el("export");
  button.disabled = true;
  try {
    const res = await fetch("./finish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows: state.saved }),
    });
    if (!res.ok) throw new Error(`${res.status}`);
    const info = await res.json();
    el("doneSummary").textContent =
      `已写入 ${info.added} 条(manifest 共 ${info.manifest_rows} 条)。` +
      `下一步:人听录音填 expected_keywords 与 intended,` +
      `再标 responses CSV 的 delivered —— 两者都不能从提示词推。`;
  } catch (err) {
    button.disabled = false;
    el("doneSummary").textContent = `导出失败: ${err?.message || err}`;
  }
}

async function begin() {
  const speaker = el("speaker").value.trim();
  const l1 = el("l1").value.trim();
  if (!/^[A-Za-z0-9_-]{2,16}$/.test(speaker)) {
    el("setupStatus").textContent = "代号只能用字母数字和 - _,2–16 位。";
    return;
  }
  if (!/^[A-Za-z-]{2,8}$/.test(l1)) {
    el("setupStatus").textContent = "母语填语言代码,例 zh / ja / es。";
    return;
  }
  el("setupStatus").textContent = "载入场景…";
  let scenarios;
  try {
    scenarios = await loadScenarios();
  } catch (err) {
    el("setupStatus").textContent = `载入失败: ${err?.message || err}`;
    return;
  }
  const plan = planFromQuery();
  const queue = buildQueue(scenarios, plan, speaker);
  if (!queue.length) {
    el("setupStatus").textContent = `没有匹配的场景: ${JSON.stringify(plan)}`;
    return;
  }
  state.speaker = speaker;
  state.l1 = l1;
  state.queue = queue;
  state.index = 0;
  el("setup").hidden = true;
  el("stage").hidden = false;
  renderCurrent();
}

el("load").addEventListener("click", begin);
el("rec").addEventListener("click", toggleRecord);
el("replay").addEventListener("click", () => el("player").play());
el("redo").addEventListener("click", () => {
  discardPending();
  renderCurrent();
});
el("next").addEventListener("click", saveAndAdvance);
el("export").addEventListener("click", exportManifest);
