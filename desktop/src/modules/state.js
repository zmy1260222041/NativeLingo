export function createStore(initialState) {
  let state = JSON.parse(JSON.stringify(initialState));
  const listeners = new Set();

  return {
    get() {
      return state;
    },
    patch(next) {
      const previous = state;
      state = { ...state, ...next };
      listeners.forEach((listener) => listener(state, previous));
      return state;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export const appStore = createStore({
  module: "speaking",
  speakingMode: "video",
  theme: "light",
  backend: { state: "starting", label: "正在启动" },
  speakingStage: "idle",
  speakingContext: {},
  memoView: "upload",
  memoStage: "upload",
  memoContext: {},
});
