export function scoreColor(score) {
  if (score >= 75) return "var(--good)";
  if (score >= 60) return "var(--weak)";
  return "var(--bad)";
}

export function clampScore(score) {
  return Math.max(0, Math.min(100, Number(score) || 0));
}

export function formatSpeechRate(ratio) {
  const safeRatio = Number.isFinite(Number(ratio)) ? Number(ratio) : 1;
  const comparison = safeRatio > 1.15
    ? "节奏偏慢"
    : safeRatio < 0.85
      ? "节奏偏快"
      : "节奏接近参考";
  return `语速为参考的 ${safeRatio.toFixed(2)} 倍，${comparison}`;
}

export function feedbackIndex(current, delta, length) {
  if (length < 1) return 0;
  return (current + delta + length) % length;
}
