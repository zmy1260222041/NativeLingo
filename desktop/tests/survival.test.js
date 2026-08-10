import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  assertNoUncalibratedScore,
  correctableWords,
  rewardLine,
  setSurvivalStage,
  SURVIVAL_FORBIDDEN_FIELDS,
  SURVIVAL_STAGES,
  SURVIVAL_TIERS,
  slotSummary,
  withHints,
} from "../src/modules/survival.js";
import { appStore } from "../src/modules/state.js";

const readSrc = (rel) => fs.readFileSync(path.resolve(process.cwd(), rel), "utf8");

describe("survival stage machine", () => {
  it("mirrors the stage onto the document for CSS and rejects unknown stages", () => {
    setSurvivalStage("recording", { scenarioId: "food-ask-bread" });
    expect(document.documentElement.dataset.survivalStage).toBe("recording");
    expect(appStore.get().survivalStage).toBe("recording");
    expect(appStore.get().survivalContext).toEqual({ scenarioId: "food-ask-bread" });
    expect(() => setSurvivalStage("winning")).toThrow(/Unknown survival stage/);
  });

  it("covers the four beta screens plus judging and failure", () => {
    ["situation", "recording", "judging", "result", "correcting", "error"].forEach((stage) => {
      expect(SURVIVAL_STAGES).toContain(stage);
    });
  });

  it("names the four tiers of the design", () => {
    expect(SURVIVAL_TIERS.map((t) => t.id)).toEqual([
      "infant", "toddler", "youth", "professional",
    ]);
  });
});

describe("红线 3 — no uncalibrated score reaches the interface", () => {
  it("throws when a payload carries a score whose threshold is unfixed until G7", () => {
    SURVIVAL_FORBIDDEN_FIELDS.forEach((field) => {
      expect(() => assertNoUncalibratedScore({ delivery: 85, [field]: 70 }, "test"))
        .toThrow(new RegExp(field));
    });
  });

  it("passes delivery through — it is G1's own criterion, not an estimate", () => {
    const payload = { delivery: 85.0, delivered: true, transcript: "i want bread" };
    expect(assertNoUncalibratedScore(payload)).toBe(payload);
  });

  it("keeps fluency and 地道度 out of the markup and the controller", () => {
    const html = readSrc("src/index.html");
    const pane = html.slice(html.indexOf('id="module-survival"'));
    ["流利", "地道", "自然度", "fluency", "naturalness"].forEach((term) => {
      expect(pane).not.toContain(term);
    });
    // The controller must not read those fields off a response either.
    const main = readSrc("src/main.js");
    const block = main.slice(main.indexOf("// SURVIVAL"), main.indexOf("// Init"));
    ["data.fluency", "data.naturalness", "data.accuracy"].forEach((expr) => {
      expect(block).not.toContain(expr);
    });
  });
});

describe("slot rendering", () => {
  it("keeps optional slots visible and marked, not hidden", () => {
    const slots = [
      { key: "need_object", required: true, hit: true, matched: ["bread"] },
      { key: "politeness", required: false, hit: false, matched: [] },
    ];
    const summary = slotSummary(slots);
    expect(summary).toHaveLength(2);
    expect(summary[1].required).toBe(false);
  });

  it("takes the Chinese hint from the scenario, which the attempt does not resend", () => {
    const merged = withHints(
      [{ key: "need_object", required: true, hit: true, matched: ["bread"] }],
      [{ key: "need_object", required: true, zh_hint: "你要的东西" }],
    );
    expect(merged[0].label).toBe("你要的东西");
  });

  it("falls back to the key when no hint exists rather than rendering blank", () => {
    const merged = withHints([{ key: "need_object", required: true, hit: false }], []);
    expect(merged[0].label).toBe("need_object");
  });

  it("tolerates a missing or malformed slot list", () => {
    expect(slotSummary()).toEqual([]);
    expect(slotSummary([{}])[0]).toMatchObject({ hit: false, required: false, matched: [] });
  });
});

describe("reward wording", () => {
  it("names what the NPC handed over, with counts above one", () => {
    expect(rewardLine({ quality: "generous", items: [{ id: "bread", count: 2 }] }))
      .toContain("bread x2");
    expect(rewardLine({ quality: "plain", items: [{ id: "bread", count: 1 }] }))
      .toContain("bread");
  });

  it("reads as an invitation to retry, never as a penalty (§5.4 retries are free)", () => {
    const line = rewardLine({ quality: null, items: [] });
    expect(line).toContain("再说一次");
    expect(line).not.toMatch(/失败|错|扣/);
    expect(rewardLine(undefined)).toBe(line);
  });
});

describe("correction entry (FR-27)", () => {
  it("splits on whitespace, matching the backend's normalise so taps match the matcher", () => {
    expect(correctableWords("  me   want bread ")).toEqual(["me", "want", "bread"]);
    expect(correctableWords("")).toEqual([]);
    expect(correctableWords(null)).toEqual([]);
  });
});

describe("beta scope is enforced in the shipped markup", () => {
  it("mounts the module in the nav and as a pane", () => {
    const html = readSrc("src/index.html");
    expect(html).toContain('data-module="survival"');
    expect(html).toContain('id="module-survival"');
  });

  it("states that recordings stay on the device", () => {
    expect(readSrc("src/index.html")).toContain("不会离开设备");
  });

  it("calls no endpoint outside the beta's four, and nothing off-device", () => {
    const main = readSrc("src/main.js");
    const block = main.slice(main.indexOf("// SURVIVAL"), main.indexOf("// Init"));
    expect(block).toContain("/game/scenario");
    expect(block).toContain("/game/attempt");
    expect(block).toContain("/correct");
    expect(block).not.toContain("/game/review");   // FR-23, out of scope
    expect(block).not.toMatch(/https?:\/\/(?!127\.0\.0\.1)/);  // zero outbound surface
  });

  it("routes HTTP through runtime.js instead of re-implementing auth or timeouts", () => {
    const main = readSrc("src/main.js");
    const block = main.slice(main.indexOf("// SURVIVAL"), main.indexOf("// Init"));
    expect(block).toContain("deadlineFetch");
    expect(block).toContain("authHeaders()");
    expect(block).not.toContain("Bearer ");   // token never hand-assembled here
    expect(block).not.toContain("XMLHttpRequest");
  });

  it("reuses the shared recorder so collected clips match the production path", () => {
    const main = readSrc("src/main.js");
    const block = main.slice(main.indexOf("// SURVIVAL"), main.indexOf("// Init"));
    expect(block).toContain("createRecorder()");
  });
});
