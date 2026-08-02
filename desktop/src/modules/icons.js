const symbols = {
  speaking: '<path d="M5 12h2m2-4v8m4-11v14m4-10v6m2-3h2"/>',
  camera: '<path d="M4 8.5h3l1.4-2h7.2l1.4 2h3v10H4z"/><circle cx="12" cy="13.5" r="3.2"/>',
  video: '<rect x="3.5" y="6" width="12" height="12" rx="2"/><path d="m15.5 10 5-2.5v9l-5-2.5z"/>',
  audio: '<path d="M4 14h3l4 3V7L7 10H4z"/><path d="M15 9.5c1.5 1.4 1.5 3.6 0 5m2.8-7.6a7.2 7.2 0 0 1 0 10.2"/>',
  theme: '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 0 0 16z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 10.5v6m0-9.2v.2"/>',
  upload: '<path d="M12 16V4m-4 4 4-4 4 4"/><path d="M5 14v5h14v-5"/>',
  record: '<circle cx="12" cy="12" r="5.2" fill="currentColor" stroke="none"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none"/>',
  replay: '<path d="M6.6 8H3.5V4.8"/><path d="M4 8a8 8 0 1 1 .5 9"/>',
  play: '<path d="m9 7 8 5-8 5z" fill="currentColor" stroke="none"/>',
  back: '<path d="m14.5 6-6 6 6 6"/>',
  local: '<path d="M7 18.5h10M9.5 15h5"/><rect x="4" y="4" width="16" height="11" rx="2"/>',
  close: '<path d="m7 7 10 10M17 7 7 17"/>',
  chevronLeft: '<path d="m14.5 6-6 6 6 6"/>',
  chevronRight: '<path d="m9.5 6 6 6-6 6"/>',
};

export function iconSvg(name, className = "icon") {
  const body = symbols[name];
  if (!body) throw new Error(`Unknown icon: ${name}`);
  return `<svg class="${className}" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
}

export function setIconButton(button, name, label, text = "") {
  if (!button) return;
  button.innerHTML = `${iconSvg(name)}${text ? `<span>${text}</span>` : ""}`;
  button.setAttribute("aria-label", label);
  if (text) delete button.dataset.tooltip;
  else button.dataset.tooltip = label;
}
