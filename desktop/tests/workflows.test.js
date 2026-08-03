import { afterEach, describe, expect, it, vi } from "vitest";
import { setStatus, makeTimer, runCountdown } from "../src/modules/recording.js";
import { feedbackIndex, formatSpeechRate, scoreColor } from "../src/modules/results.js";
import { selectedRangeLabel, setSpeakingStage } from "../src/modules/speaking.js";
import { countObjectLabels, setMemoStage } from "../src/modules/memorizing.js";
import { appStore } from "../src/modules/state.js";
import { containRect, objectsAtPoint } from "../src/modules/geometry.js";

afterEach(() => {
  vi.useRealTimers();
});

describe("speaking workflow", () => {
  it("formats the two-click sentence range without separator copy", () => {
    expect(selectedRangeLabel(0, null)).toBe("起点为第 1 句");
    expect(selectedRangeLabel(0, 2)).toBe("第 1 至 3 句，共 3 句");
  });

  it("records explicit workflow stages", () => {
    setSpeakingStage("recording", { mode: "video" });
    expect(appStore.get().speakingStage).toBe("recording");
    expect(document.documentElement.dataset.speakingStage).toBe("recording");
    expect(() => setSpeakingStage("unknown")).toThrow(/Unknown speaking stage/);
  });
});

describe("results workflow", () => {
  it("normalizes score colors and feedback navigation", () => {
    expect(scoreColor(90)).toBe("var(--good)");
    expect(scoreColor(68)).toBe("var(--weak)");
    expect(scoreColor(40)).toBe("var(--bad)");
    expect(feedbackIndex(0, -1, 3)).toBe(2);
    expect(feedbackIndex(2, 1, 3)).toBe(0);
  });

  it("explains speaking rate in compact Chinese", () => {
    expect(formatSpeechRate(1.2)).toContain("节奏偏慢");
    expect(formatSpeechRate(0.8)).toContain("节奏偏快");
    expect(formatSpeechRate(1)).toContain("节奏接近参考");
  });
});

describe("memorizing workflow", () => {
  it("counts repeated vocabulary and tracks the current surface", () => {
    const counts = countObjectLabels([
      { label_en: "lamp" },
      { label_en: "book" },
      { label_en: "lamp" },
    ]);
    expect([...counts.entries()]).toEqual([["lamp", 2], ["book", 1]]);
    setMemoStage("detail", { object: "lamp" });
    expect(appStore.get().memoStage).toBe("detail");
    expect(document.documentElement.dataset.memoStage).toBe("detail");
  });

  it("maps portrait media inside a letterboxed stage without stretching", () => {
    expect(containRect(900, 620, 900, 1600)).toEqual({
      x: 275.625,
      y: 0,
      width: 348.75,
      height: 620,
      scale: 0.3875,
    });
  });

  it("orders overlapping objects from the most specific box", () => {
    const objects = [
      { label_en: "table", box: [0, 0, 900, 900] },
      { label_en: "cup", box: [200, 200, 300, 300] },
      { label_en: "handle", box: [320, 260, 80, 120] },
    ];
    expect(objectsAtPoint(objects, 350, 300).map((object) => object.label_en))
      .toEqual(["handle", "cup", "table"]);
  });
});

describe("recording feedback", () => {
  it("keeps status feedback in place and advances the timer", async () => {
    vi.useFakeTimers();
    document.body.innerHTML = '<span id="timer"></span><span id="status"></span>';
    const status = document.getElementById("status");
    setStatus(status, "prep", "正在准备麦克风");
    expect(status.className).toBe("analyze-status prep");

    const timer = makeTimer("timer");
    timer.start();
    expect(document.getElementById("timer").textContent).toBe("00:00");
    await vi.advanceTimersByTimeAsync(2000);
    expect(document.getElementById("timer").textContent).toBe("00:02");
    timer.stop();

    const ticks = [];
    const countdown = runCountdown(status, 2, (remaining) => ticks.push(remaining));
    expect(status.textContent).toBe("2");
    await vi.advanceTimersByTimeAsync(2000);
    await countdown;
    expect(status.textContent).toBe("1");
    expect(ticks).toEqual([2, 1]);
  });
});
