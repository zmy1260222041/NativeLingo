import { UI_COPY } from "./copy.js";
import { setIconButton } from "./icons.js";
import { revealView } from "./motion.js";
import { appStore } from "./state.js";
import { setMemoStage } from "./memorizing.js";

const byId = (id) => document.getElementById(id);

function toggleSystemPanel(force) {
  const panel = byId("system-panel");
  const triggers = [byId("backend-status"), byId("info-toggle")].filter(Boolean);
  const open = typeof force === "boolean" ? force : panel.hidden;
  panel.hidden = !open;
  triggers.forEach((trigger) => trigger.setAttribute("aria-expanded", String(open)));
  if (open) revealView(panel);
}

export function wireEditorialShell() {
  const moduleIcons = { speaking: "speaking", memorize: "camera" };
  document.querySelectorAll(".module").forEach((button) => {
    const label = button.dataset.module === "speaking" ? UI_COPY.speaking : UI_COPY.memorize;
    setIconButton(button, moduleIcons[button.dataset.module], label, label);
  });
  document.querySelectorAll(".tab").forEach((button) => {
    const video = button.dataset.mode === "video";
    const label = video ? UI_COPY.videoMode : UI_COPY.audioMode;
    setIconButton(button, video ? "video" : "audio", label, label);
  });
  document.querySelectorAll(".info-button").forEach((button) => {
    setIconButton(button, "info", button.getAttribute("aria-label") || "查看说明");
  });
  setIconButton(byId("info-toggle"), "info", "应用信息");
  setIconButton(byId("system-panel-close"), "close", "关闭应用信息");
  setIconButton(byId("shadow-replay-btn"), "replay", "重放画面");
  setIconButton(byId("shadow-record-btn"), "record", "开始跟读");
  setIconButton(byId("record-btn"), "record", "开始录音");
  setIconButton(byId("memo-back"), "back", "返回整图");
  setIconButton(byId("memo-pronounce-record"), "record", "开始录音");

  byId("backend-status").addEventListener("click", () => toggleSystemPanel());
  byId("info-toggle").addEventListener("click", () => toggleSystemPanel());
  byId("system-panel-close").addEventListener("click", () => toggleSystemPanel(false));

  document.querySelectorAll(".inspector-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const view = tab.dataset.inspectorView;
      document.querySelectorAll(".inspector-tab").forEach((item) => {
        const active = item === tab;
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      document.querySelectorAll("[data-inspector-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.inspectorPanel !== view;
      });
      setMemoStage(
        view === "practice" ? "practicing" : view === "context" ? "scenario" : "detail",
      );
      revealView(document.querySelector(`[data-inspector-panel="${view}"]`));
    });
  });
}

export function wireTheme() {
  const toggle = byId("theme-toggle");
  const apply = (dark) => {
    document.documentElement.classList.toggle("dark", dark);
    const label = dark ? "切换到浅色主题" : "切换到深色主题";
    setIconButton(toggle, "theme", label);
    appStore.patch({ theme: dark ? "dark" : "light" });
  };
  toggle.addEventListener("click", () => {
    const nextDark = !document.documentElement.classList.contains("dark");
    apply(nextDark);
    try { localStorage.setItem("nl-theme", nextDark ? "dark" : "light"); } catch (_) {}
  });
  apply(document.documentElement.classList.contains("dark"));
}
