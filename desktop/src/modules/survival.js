import { appStore } from "./state.js";

// Survival module — internal-beta collection build (FR-22/25/27).
//
// Four screens only: Chinese situation -> record -> transcript + slot hits +
// NPC reply + supplies -> word-level correction. Everything else in the design
// (cloud judging FR-23, photo vocabulary FR-24, the supply economy FR-26) is
// out of scope this round; the build exists to produce the corpus R-14's G1 and
// G2 need, not to ship the game.
//
// 红线 3 lives here: the only number rendered is `delivery`, which is the
// deterministic slot-hit rate and therefore G1's criterion itself. No fluency,
// naturalness or 地道度 — their thresholds are unfixed until G7, and showing one
// now would dress an uncalibrated number as a finished score. Keep
// SURVIVAL_FORBIDDEN_FIELDS in sync with anything the backend starts sending;
// tests/survival.test.js asserts none of them reach the DOM.
export const SURVIVAL_STAGES = Object.freeze([
  "idle",
  "situation",
  "recording",
  "judging",
  "result",
  "correcting",
  "error",
]);

export const SURVIVAL_FORBIDDEN_FIELDS = Object.freeze([
  "fluency",
  "naturalness",
  "idiomaticity",
  "nativeness",
  "accuracy",
]);

export function setSurvivalStage(stage, context = {}) {
  if (!SURVIVAL_STAGES.includes(stage)) throw new Error(`Unknown survival stage: ${stage}`);
  const next = appStore.patch({ survivalStage: stage, survivalContext: context });
  document.documentElement.dataset.survivalStage = stage;
  return next;
}

export const SURVIVAL_TIERS = Object.freeze([
  { id: "infant", label: "婴儿" },
  { id: "toddler", label: "幼儿" },
  { id: "youth", label: "少年" },
  { id: "professional", label: "成人" },
]);

/** Slot summary for the result screen: which required meanings landed.
 *
 * Optional slots are marked as such rather than hidden — they move the reward
 * band but never decide whether the meaning got across, and a learner who
 * cannot see that distinction will read a missed optional slot as a failure. */
export function slotSummary(slots = []) {
  return slots.map((slot) => ({
    key: slot?.key || "",
    required: Boolean(slot?.required),
    hit: Boolean(slot?.hit),
    matched: Array.isArray(slot?.matched) ? slot.matched : [],
    label: slot?.zh_hint || slot?.key || "",
  }));
}

/** Merge the zh hints from /game/scenario into the slot verdicts from
 * /game/attempt. The attempt response carries no hints (the backend does not
 * resend scenario text per attempt), so the hint has to come from the scenario
 * the learner is currently on. */
export function withHints(slots = [], hints = []) {
  const byKey = new Map(hints.map((h) => [h?.key, h?.zh_hint || ""]));
  return slotSummary(slots).map((slot) => ({
    ...slot,
    label: byKey.get(slot.key) || slot.label,
  }));
}

/** Reward wording. `null` quality means the attempt earned nothing — which is
 * NOT a punishment: §5.4 makes retries free, so the honest line is "say it
 * again", not a score. */
export function rewardLine(reward) {
  const quality = reward?.quality || null;
  const items = Array.isArray(reward?.items) ? reward.items : [];
  if (!quality || items.length === 0) return "对方没听明白，可以再说一次";
  const listed = items
    .map((item) => (item?.count > 1 ? `${item.id} x${item.count}` : item?.id))
    .filter(Boolean)
    .join("、");
  const prefix = { generous: "对方多给了你", plain: "对方给了你", scrap: "对方给了你一点" }[quality]
    || "对方给了你";
  return `${prefix}：${listed}`;
}

/** Words the learner can flag as misheard, split from the transcript.
 *
 * The correction entry is the (A)/(B) triage: if the instrument lost a word the
 * learner did say, that is G2's business; if the learner never produced it, the
 * route is the Speaking module. Splitting on whitespace matches the backend's
 * normalise(), so what the learner taps is what the matcher saw. */
export function correctableWords(transcript = "") {
  return String(transcript || "")
    .split(/\s+/)
    .filter(Boolean);
}

/** Guard for 红线 3: throws if a payload field would put an uncalibrated score
 * on screen. Called on every backend response the module renders, so a future
 * endpoint change cannot quietly leak one. */
export function assertNoUncalibratedScore(payload, where = "payload") {
  const leaked = SURVIVAL_FORBIDDEN_FIELDS.filter((field) => field in (payload || {}));
  if (leaked.length) {
    throw new Error(`${where} carries uncalibrated score field(s): ${leaked.join(", ")}`);
  }
  return payload;
}
