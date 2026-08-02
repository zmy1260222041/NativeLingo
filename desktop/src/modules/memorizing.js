import { appStore } from "./state.js";

export const MEMO_PREPROCESSING_CONTRACT = "memorize-image-v1";
export const MEMO_STAGES = Object.freeze([
  "upload",
  "analyzing",
  "photo",
  "detail",
  "practicing",
  "scenario",
  "error",
]);

export function setMemoStage(stage, context = {}) {
  if (!MEMO_STAGES.includes(stage)) throw new Error(`Unknown memorizing stage: ${stage}`);
  const next = appStore.patch({ memoStage: stage, memoContext: context });
  document.documentElement.dataset.memoStage = stage;
  return next;
}

export function countObjectLabels(objects = []) {
  const counts = new Map();
  objects.forEach((object) => {
    const label = object?.label_en;
    if (label) counts.set(label, (counts.get(label) || 0) + 1);
  });
  return counts;
}
