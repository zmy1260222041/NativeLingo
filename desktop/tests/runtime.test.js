import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  delete window.__NATIVELINGO_BACKEND__;
  delete window.__NATIVELINGO_TOKEN__;
  vi.resetModules();
});

describe("local API runtime", () => {
  it("adds the per-launch authorization token", async () => {
    window.__NATIVELINGO_BACKEND__ = "http://127.0.0.1:9400";
    window.__NATIVELINGO_TOKEN__ = "session-token";
    global.fetch = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    const { apiFetch } = await import("../src/modules/runtime.js");

    await apiFetch("/health", { headers: { "X-Test": "yes" } });

    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:9400/health");
    expect(options.headers.get("Authorization")).toBe("Bearer session-token");
    expect(options.headers.get("X-Test")).toBe("yes");
  });

  it("turns a stalled local request into a recoverable timeout", async () => {
    vi.useFakeTimers();
    global.fetch = vi.fn((_, options) => new Promise((resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
    const { deadlineFetch } = await import("../src/modules/runtime.js");

    const request = deadlineFetch("/memorize/analyze", {}, 250);
    const assertion = expect(request).rejects.toMatchObject({ name: "RequestTimeoutError" });
    await vi.advanceTimersByTimeAsync(250);

    await assertion;
  });

  it("normalizes backend errors into one client error shape", async () => {
    const { readJson } = await import("../src/modules/runtime.js");
    const response = new Response(JSON.stringify({ detail: "模型尚未准备好" }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });

    await expect(readJson(response, "分析失败")).rejects.toMatchObject({
      name: "ApiError",
      message: "模型尚未准备好",
      status: 503,
    });
  });
});
