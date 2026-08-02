import { appStore } from "./state.js";

export const SPEAKING_STAGES = Object.freeze([
  "idle",
  "source-ready",
  "range-started",
  "range-ready",
  "preparing",
  "recording",
  "recorded",
  "analyzing",
  "results",
  "error",
]);

export function setSpeakingStage(stage, context = {}) {
  if (!SPEAKING_STAGES.includes(stage)) throw new Error(`Unknown speaking stage: ${stage}`);
  const next = appStore.patch({ speakingStage: stage, speakingContext: context });
  document.documentElement.dataset.speakingStage = stage;
  return next;
}

export function selectedRangeLabel(start, end) {
  if (start == null) return "";
  if (end == null) return `起点为第 ${start + 1} 句`;
  return `第 ${start + 1} 至 ${end + 1} 句，共 ${end - start + 1} 句`;
}
