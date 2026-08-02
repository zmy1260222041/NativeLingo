import { expect, test } from "@playwright/test";

const transparentPng = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

const analysisResult = {
  overall_score: 82,
  accuracy: 78,
  fluency: 86,
  speech_rate_ratio: 1.02,
  reference_text: "First line for practice. Second line for practice.",
  tips: ["收紧 line 的元音结尾"],
  prosody: {
    intonation_match: 84,
    pause_match: 79,
    learner_pauses: 1,
    reference_pauses: 1,
  },
  segment: { start: 0, end: 4.8 },
  sentences: [
    {
      accuracy: 74,
      fluency: 83,
      start: 0,
      end: 2.2,
      learner_start: 0,
      learner_end: 2.1,
      words: [
        { word: "First", status: "good", accuracy: 90, start: 0, end: 0.5, learner_start: 0, learner_end: 0.45 },
        { word: "line", status: "weak", accuracy: 63, tip: "元音结尾再短一些", start: 0.5, end: 1, learner_start: 0.45, learner_end: 1 },
        { word: "for", status: "good", accuracy: 86, start: 1, end: 1.35, learner_start: 1, learner_end: 1.35 },
        { word: "practice", status: "weak", accuracy: 68, tip: "重音落在前半段", start: 1.35, end: 2.2, learner_start: 1.35, learner_end: 2.1 },
      ],
    },
  ],
};

async function installMediaMocks(page) {
  await page.addInitScript(() => {
    class MockMediaRecorder {
      static isTypeSupported() { return true; }
      constructor(stream, options = {}) {
        this.stream = stream;
        this.mimeType = options.mimeType || "audio/webm";
        this.state = "inactive";
      }
      start() { this.state = "recording"; }
      requestData() {
        this.ondataavailable?.({ data: new Blob(["voice"], { type: this.mimeType }) });
      }
      stop() {
        this.state = "inactive";
        queueMicrotask(() => this.onstop?.());
      }
    }
    Object.defineProperty(window, "MediaRecorder", { value: MockMediaRecorder, configurable: true });
    Object.defineProperty(navigator, "mediaDevices", {
      value: {
        getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }),
      },
      configurable: true,
    });
    HTMLMediaElement.prototype.play = async function play() {};
    HTMLMediaElement.prototype.pause = function pause() {};
  });
}

async function mockBackend(page) {
  await page.route("http://127.0.0.1:8756/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const headers = { "Access-Control-Allow-Origin": "*", "Content-Type": "application/json" };
    const json = (body) => route.fulfill({ status: 200, headers, body: JSON.stringify(body) });

    if (request.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: { ...headers, "Access-Control-Allow-Headers": "*" } });
    }
    if (path === "/health") return json({ status: "ok", model_loaded: true });
    if (path === "/warmup") return json({ stage: "done" });
    if (path === "/videos") return json({ videos: [{ name: "demo.mp4", size_mb: 7.4 }] });
    if (path.endsWith("/process")) {
      return json({
        sentences: [
          { index: 0, start: 0, end: 2.2, text: "First line for practice." },
          { index: 1, start: 2.2, end: 4.8, text: "Second line for practice." },
        ],
      });
    }
    if (path === "/analyze" || path === "/analyze_video") return json(analysisResult);
    if (path === "/recordings") return json({ recording_id: "recording-1" });
    if (path === "/memorize/status") return json({ stage: "done", running: false });
    if (path === "/memorize/warmup" || path === "/memorize/release") return json({ status: "ok" });
    if (path === "/memorize/analyze") {
      return json({
        preprocessing: "memorize-image-v1",
        photo_id: "photo-1",
        image_size: [1, 1],
        objects: [{ id: "lamp-1", label_en: "lamp", label_zh: "灯", box: [0, 0, 1, 1] }],
      });
    }
    if (path === "/memorize/parts") {
      return json({
        is_container: false,
        crop_box: [0, 0, 1, 1],
        parts: [{ label_en: "shade", label_zh: "灯罩", box: [0, 0, 1, 1] }],
        contents: [],
      });
    }
    if (path === "/memorize/scenario") {
      return json({
        scene: "At home in the evening",
        turns: [
          { speaker: "A", en: "Could you turn on the lamp?", zh: "你能打开灯吗？" },
          { speaker: "B", en: "Sure, it is beside the sofa.", zh: "可以，它在沙发旁边。" },
        ],
      });
    }
    if (path === "/memorize/pronounce/status") return json({ status: "ok", ready: true });
    if (path === "/memorize/pronounce") return json({ accuracy: 88, fluency: 81 });
    if (path.includes("/stream")) return route.fulfill({ status: 200, body: "" });
    return json({ status: "ok" });
  });
}

test.beforeEach(async ({ page }) => {
  await installMediaMocks(page);
  await mockBackend(page);
});

for (const viewport of [
  { width: 600, height: 720 },
  { width: 760, height: 900 },
  { width: 1024, height: 900 },
]) {
  test(`editorial shell fits ${viewport.width} by ${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByRole("button", { name: "demo.mp4" })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      viewport: window.innerWidth,
      document: document.documentElement.scrollWidth,
    }));
    expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
    const undersizedButtons = await page.locator("button:visible").evaluateAll((buttons) =>
      buttons
        .map((button) => ({
          name: button.getAttribute("aria-label") || button.textContent.trim(),
          width: button.getBoundingClientRect().width,
          height: button.getBoundingClientRect().height,
        }))
        .filter(({ width, height }) => width < 44 || height < 44),
    );
    expect(undersizedButtons).toEqual([]);
    await expect(page).toHaveScreenshot(`speaking-${viewport.width}.png`, { fullPage: true });
  });
}

test("switches themes and keeps module navigation explicit", async ({ page }) => {
  await page.setViewportSize({ width: 760, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "切换到深色主题" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.getByRole("button", { name: "识物" }).click();
  await expect(page.getByRole("heading", { name: /把眼前事物/ })).toBeVisible();
  await expect(page).toHaveScreenshot("memorize-dark.png", { fullPage: true });
});

test("preserves the speaking range and memorizing detail flows", async ({ page }) => {
  await page.setViewportSize({ width: 760, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "demo.mp4" }).click();
  await expect(page.getByText("First line for practice.")).toBeVisible();
  const sentences = page.locator(".sentence-item");
  await sentences.nth(0).click();
  await sentences.nth(1).click();
  await expect(page.getByText("第 1 至 2 句，共 2 句")).toBeVisible();
  await expect(page.locator("#shadow-section")).toBeVisible();

  await page.getByRole("button", { name: "识物" }).click();
  await page.locator("#memo-file").setInputFiles({ name: "room.png", mimeType: "image/png", buffer: transparentPng });
  await expect(page.getByRole("button", { name: "查看物品 lamp" })).toBeVisible();
  await page.getByRole("button", { name: "查看物品 lamp" }).click();
  await expect(page.locator("#memo-detail-label")).toHaveText("lamp");
  await page.locator('.inspector-tab[data-inspector-view="practice"]').click();
  await expect(page.locator("#memo-pronounce-hint")).toHaveText("lamp");
  await page.getByRole("button", { name: "开始录音" }).click();
  await page.getByRole("button", { name: "停止录音" }).click();
  await expect(page.getByText("本地声学对比结果")).toBeVisible();
  await page.getByRole("button", { name: "情景" }).click();
  await expect(page.getByText("Could you turn on the lamp?")).toBeVisible();
});

test("records a selected video range and renders stacked feedback", async ({ page }) => {
  test.setTimeout(15_000);
  await page.setViewportSize({ width: 760, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "demo.mp4" }).click();
  const sentences = page.locator(".sentence-item");
  await sentences.nth(0).click();
  await sentences.nth(1).click();
  await page.getByRole("button", { name: "开始跟读" }).click();
  await expect(page.getByRole("button", { name: "停止跟读" })).toBeVisible({ timeout: 5_000 });
  await page.getByRole("button", { name: "停止跟读" }).click();
  await expect(page.getByRole("button", { name: "开始分析" })).toBeEnabled();
  await page.getByRole("button", { name: "开始分析" }).click();
  await expect(page.locator("#overall-score")).toHaveText("82");
  await expect(page.getByRole("button", { name: "下一条反馈" })).toBeVisible();
  await page.evaluate(() => document.activeElement?.blur());
  await expect(page).toHaveScreenshot("results-light.png");
});

test("keeps audio upload and analysis in the same workbench", async ({ page }) => {
  test.setTimeout(15_000);
  await page.setViewportSize({ width: 760, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "音频" }).click();
  await page.locator("#ref-file").setInputFiles({
    name: "reference.wav",
    mimeType: "audio/wav",
    buffer: Buffer.from("reference"),
  });
  await page.getByRole("button", { name: "开始录音" }).click();
  await expect(page.getByRole("button", { name: "停止录音" })).toBeVisible({ timeout: 5_000 });
  await page.getByRole("button", { name: "停止录音" }).click();
  await expect(page.locator("#analyze-btn")).toBeEnabled();
  await page.locator("#analyze-btn").click();
  await expect(page.locator("#overall-score")).toHaveText("82");
});

test("shows a recoverable empty recognition state", async ({ page }) => {
  await page.route("http://127.0.0.1:8756/memorize/analyze", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        preprocessing: "memorize-image-v1",
        photo_id: "empty-photo",
        image_size: [1, 1],
        objects: [],
      }),
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "识物" }).click();
  await page.locator("#memo-file").setInputFiles({ name: "empty.png", mimeType: "image/png", buffer: transparentPng });
  await expect(page.getByText(/没有识别到明确的物品/)).toBeVisible();
  await expect(page.getByRole("button", { name: "换张照片" })).toBeVisible();
});

test("ignores an expired recognition response", async ({ page }) => {
  let analyzeCall = 0;
  await page.route("http://127.0.0.1:8756/memorize/analyze", async (route) => {
    analyzeCall += 1;
    const first = analyzeCall === 1;
    if (first) await new Promise((resolve) => setTimeout(resolve, 250));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        preprocessing: "memorize-image-v1",
        photo_id: first ? "stale-photo" : "current-photo",
        image_size: [1, 1],
        objects: [{
          id: first ? "lamp-1" : "chair-1",
          label_en: first ? "lamp" : "chair",
          box: [0, 0, 1, 1],
        }],
      }),
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "识物" }).click();
  const input = page.locator("#memo-file");
  await input.setInputFiles({ name: "first.png", mimeType: "image/png", buffer: transparentPng });
  await input.setInputFiles({ name: "second.png", mimeType: "image/png", buffer: transparentPng });
  await expect(page.getByRole("button", { name: "查看物品 chair" })).toBeVisible();
  await expect(page.getByRole("button", { name: "查看物品 lamp" })).toHaveCount(0);
});

test("enters and releases the memorizing models with module navigation", async ({ page }) => {
  const requestedPaths = [];
  page.on("request", (request) => requestedPaths.push(new URL(request.url()).pathname));
  await page.goto("/");
  await page.getByRole("button", { name: "识物" }).click();
  await expect.poll(() => requestedPaths).toContain("/memorize/warmup");
  await page.locator('[data-module="speaking"]').click();
  await expect.poll(() => requestedPaths).toContain("/memorize/release");
});

test("keeps focus visible with reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 760, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "识物" }).focus();
  await expect(page.getByRole("button", { name: "识物" })).toBeFocused();
  await expect(page).toHaveScreenshot("keyboard-reduced-motion.png", { fullPage: true });
});
