import { describe, expect, it, vi } from "vitest";
import { createStore } from "../src/modules/state.js";

describe("lightweight interface store", () => {
  it("publishes state transitions without mutating the previous snapshot", () => {
    const store = createStore({ module: "speaking", theme: "light" });
    const listener = vi.fn();
    store.subscribe(listener);

    const before = store.get();
    store.patch({ module: "memorize" });

    expect(store.get()).toEqual({ module: "memorize", theme: "light" });
    expect(before).toEqual({ module: "speaking", theme: "light" });
    expect(listener).toHaveBeenCalledOnce();
    expect(listener.mock.calls[0][1]).toBe(before);
  });

  it("allows subscribers to detach", () => {
    const store = createStore({ view: "upload" });
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    unsubscribe();
    store.patch({ view: "detail" });
    expect(listener).not.toHaveBeenCalled();
  });
});
