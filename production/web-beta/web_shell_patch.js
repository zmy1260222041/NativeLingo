// Stranger Web Beta — HTML shell patch injected after export, before
// build/web/index.html loads index.js.
//
// WHY THIS EXISTS
// Godot's web export calls HTMLCanvasElement.requestPointerLock() from its
// ignored-return helper. In Chrome/Edge a request issued outside the trusted
// click dispatch rejects with WrongDocumentError, and because the promise is
// never handled it becomes an uncaught page error. This patch:
//   1. keeps Godot's helper intact but swallows the rejected promise;
//   2. performs the actual first pointer-lock request inside a document-level
//      capture mousedown listener (a real trusted gesture) before Godot's own
//      canvas listeners run;
//   3. does NOT touch microphone, network, game state or any game code.
(function () {
  'use strict';
  const nativeLock = HTMLCanvasElement.prototype.requestPointerLock;

  HTMLCanvasElement.prototype.requestPointerLock = function (...args) {
    try {
      const result = nativeLock.apply(this, args);
      if (result && typeof result.catch === 'function') {
        result.catch(function () { /* pointer lock is optional input comfort */ });
      }
      return result;
    } catch (_error) {
      // Synchronous throw path: never let Godot's ignored call become an
      // uncaught page error.
      return undefined;
    }
  };

  function acquireFromTrustedGesture(canvas) {
    if (!canvas || document.pointerLockElement) return;
    try {
      const result = nativeLock.call(canvas);
      if (result && typeof result.catch === 'function') {
        result.catch(function () { /* swallowed */ });
      }
    } catch (_error) { /* swallowed */ }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      const canvas = document.getElementById('canvas');
      document.addEventListener('mousedown', function (event) {
        if (event.target === canvas) acquireFromTrustedGesture(canvas);
      }, { capture: true });
    }, { once: true });
  } else {
    const canvas = document.getElementById('canvas');
    document.addEventListener('mousedown', function (event) {
      if (event.target === canvas) acquireFromTrustedGesture(canvas);
    }, { capture: true });
  }
})();
