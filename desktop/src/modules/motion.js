import { gsap } from "gsap";
import { Flip } from "gsap/Flip";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(Flip, ScrollTrigger);

const motionMedia = gsap.matchMedia();
let motionEnabled = true;

motionMedia.add("(prefers-reduced-motion: reduce)", () => {
  motionEnabled = false;
  ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
  return () => { motionEnabled = true; };
});

motionMedia.add("(prefers-reduced-motion: no-preference)", () => {
  motionEnabled = true;
});

function canAnimate() {
  return motionEnabled;
}

export function revealView(element) {
  if (!element || !canAnimate()) return;
  gsap.fromTo(
    element,
    { autoAlpha: 0, y: 12, scale: 0.985 },
    { autoAlpha: 1, y: 0, scale: 1, duration: 0.28, ease: "power3.out", clearProps: "transform" },
  );
}

export function revealImage(element) {
  if (!element || !canAnimate()) return;
  gsap.fromTo(
    element,
    { autoAlpha: 0.35, scale: 0.86 },
    { autoAlpha: 1, scale: 1, duration: 0.62, ease: "power3.out", clearProps: "transform" },
  );
}

export function animateCountdown(container, value) {
  const digit = container?.querySelector("span");
  if (!digit) return;
  digit.textContent = String(value);
  gsap.killTweensOf(digit);
  if (!canAnimate()) {
    gsap.set(digit, { autoAlpha: 1, scale: 1 });
    return;
  }
  gsap.fromTo(
    digit,
    { autoAlpha: 0.18, scale: 0.72 },
    { autoAlpha: 1, scale: 1, duration: 0.34, ease: "power3.out" },
  );
}

export function revealHotspots(container) {
  if (!container || !canAnimate()) return;
  gsap.fromTo(
    container.children,
    { autoAlpha: 0, scale: 0.92 },
    { autoAlpha: 1, scale: 1, duration: 0.28, stagger: 0.025, ease: "power2.out" },
  );
}

export function stackResults(container) {
  if (!container) return;
  ScrollTrigger.getAll().forEach((trigger) => {
    if (trigger.vars?.id?.startsWith("nl-result-")) trigger.kill();
  });
  if (!canAnimate()) return;
  [...container.children].forEach((card, index) => {
    gsap.fromTo(
      card,
      { autoAlpha: 0.35, y: 32, scale: 0.96 },
      {
        autoAlpha: 1,
        y: 0,
        scale: 1,
        ease: "none",
        scrollTrigger: {
          id: `nl-result-${index}`,
          trigger: card,
          start: "top 88%",
          end: "top 54%",
          scrub: true,
        },
      },
    );
  });
}

export function flipLayout(elements, mutate) {
  const targets = Array.from(elements || []);
  if (!canAnimate() || !targets.length) {
    mutate();
    return;
  }
  const state = Flip.getState(targets);
  mutate();
  Flip.from(state, { duration: 0.32, ease: "power3.inOut", absolute: false });
}

export function refreshMotion() {
  if (canAnimate()) ScrollTrigger.refresh();
}
