import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { FORBIDDEN_UI_PATTERN, UI_COPY } from "../src/modules/copy.js";

describe("editorial interface copy", () => {
  it("keeps centralized interface strings free of banned separators and pictograms", () => {
    Object.values(UI_COPY).forEach((value) => {
      expect(value).not.toMatch(FORBIDDEN_UI_PATTERN);
      expect(value).not.toMatch(/^(SECTION|QUESTION)\s+\d+/i);
    });
  });

  it("gives every empty icon control an accessible name", () => {
    const html = fs.readFileSync(path.resolve(process.cwd(), "src/index.html"), "utf8");
    const parsed = new DOMParser().parseFromString(html, "text/html");
    const unnamed = [...parsed.querySelectorAll("button")].filter((button) =>
      !button.textContent.trim() && !button.getAttribute("aria-label"));
    expect(unnamed).toEqual([]);
  });

  it("does not reintroduce visible meta labels or separator glyphs", () => {
    const html = fs.readFileSync(path.resolve(process.cwd(), "src/index.html"), "utf8");
    expect(html).not.toMatch(/SECTION\s+\d+|QUESTION\s+\d+/i);
    expect(html).not.toContain("·");
  });
});
