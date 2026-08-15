#!/usr/bin/env node
// Browser-level smoke test for the exported Stranger Web Beta build.
// Serves build/web/ with correct MIME + gzip static, loads it in headless
// Chromium, and asserts:
//   - the Godot canvas boots without page errors;
//   - no request targets 127.0.0.1 / localhost / the speech service;
//   - no navigator.mediaDevices.getUserMedia call is made;
//   - basic keyboard/mouse input keeps the page alive.
// Usage: node production/web-beta/browser_smoke.mjs
'use strict';

import fs from 'fs';
import http from 'http';
import path from 'path';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', '..');
const WEB_ROOT = path.join(ROOT, 'build', 'web');
const PORT = Number(process.env.WEB_BETA_SMOKE_PORT || 17839);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript',
  '.wasm': 'application/wasm',
  '.pck': 'application/octet-stream',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.json': 'application/json',
};

function serve() {
  return http.createServer((req, res) => {
    const urlPath = decodeURIComponent((req.url || '/').split('?')[0]);
    let rel = urlPath === '/' ? 'index.html' : urlPath.replace(/^\/+/, '');
    rel = path.normalize(rel).replace(/^(\.\.[/\\])+/, '');
    const file = path.join(WEB_ROOT, rel);
    if (!file.startsWith(WEB_ROOT + path.sep) || !fs.existsSync(file)) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('not found');
      return;
    }
    const ext = path.extname(file).toLowerCase();
    const type = MIME[ext] || 'application/octet-stream';
    const acceptGzip = /gzip/.test(req.headers['accept-encoding'] || '');
    const gz = file + '.gz';
    if (acceptGzip && fs.existsSync(gz)) {
      res.writeHead(200, {
        'Content-Type': type,
        'Content-Encoding': 'gzip',
        'Vary': 'Accept-Encoding',
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
        'Permissions-Policy': 'camera=(), microphone=()',
      });
      fs.createReadStream(gz).pipe(res);
      return;
    }
    res.writeHead(200, {
      'Content-Type': type,
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Permissions-Policy': 'camera=(), microphone=()',
    });
    fs.createReadStream(file).pipe(res);
  });
}

(async () => {
  if (!fs.existsSync(path.join(WEB_ROOT, 'index.wasm'))) {
    console.error('build/web/index.wasm missing; run scripts/build_stranger_web_beta.sh first');
    process.exit(1);
  }

  const { chromium } = require(path.join(ROOT, 'desktop', 'node_modules', 'playwright'));

  const server = serve();
  await new Promise((resolve) => server.listen(PORT, '127.0.0.1', resolve));

  const requirePointerLock = process.env.WEB_BETA_HEADED === '1';
  const browser = await chromium.launch({ headless: !requirePointerLock });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const micCalls = [];
  await page.addInitScript(() => {
    window.__webBetaProbe = { micCalls: 0 };
    try {
      if (!navigator.mediaDevices) {
        Object.defineProperty(navigator, 'mediaDevices', { value: {}, configurable: true });
      }
      navigator.mediaDevices.getUserMedia = async () => {
        window.__webBetaProbe.micCalls += 1;
        throw new DOMException('blocked by web-beta probe', 'NotAllowedError');
      };
      navigator.mediaDevices.enumerateDevices = async () => {
        window.__webBetaProbe.micCalls += 1;
        return [];
      };
    } catch (_) { /* keep probing non-fatal */ }
  });

  const badRequests = [];
  page.on('request', (request) => {
    const url = request.url();
    const allowedLocal = url.startsWith(`http://127.0.0.1:${PORT}/`)
      || url.startsWith(`blob:http://127.0.0.1:${PORT}/`);
    if ((/127\.0\.0\.1|localhost|17831|\/transcribe/i.test(url)) && !allowedLocal) {
      badRequests.push(url);
    }
    if (/17831/.test(url)) badRequests.push(url);
  });

  const consoleErrors = [];
  const pageErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => pageErrors.push(String(err)));

  try {
    await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForSelector('#canvas', { timeout: 30000 });
    await page.waitForTimeout(8000);

    const canvasState = await page.evaluate(() => ({
      width: document.querySelector('#canvas')?.width || 0,
      height: document.querySelector('#canvas')?.height || 0,
      status: document.querySelector('#status')?.style.visibility || '',
      micCalls: window.__webBetaProbe ? window.__webBetaProbe.micCalls : -1,
    }));

    await page.bringToFront();
    await page.mouse.click(Math.floor(canvasState.width / 2), Math.floor(canvasState.height / 2));
    let pointerLocked = false;
    for (let i = 0; i < 12 && !pointerLocked; i++) {
      await page.waitForTimeout(250);
      pointerLocked = await page.evaluate(() => Boolean(document.pointerLockElement));
    }
    await page.keyboard.down('w'); await page.waitForTimeout(500); await page.keyboard.up('w');
    await page.keyboard.press('g'); await page.waitForTimeout(300);
    await page.keyboard.press('e'); await page.waitForTimeout(300);
    await page.keyboard.press('v'); await page.waitForTimeout(300);
    await page.waitForTimeout(1000);

    const meaningfulPageErrors = pageErrors.filter((err) =>
      !(err.includes('WrongDocumentError') && pointerLocked));

    const screenshot = path.join(ROOT, 'build', 'web-beta-smoke.png');
    await page.screenshot({ path: screenshot });

    console.log('  mode:', requirePointerLock ? 'headed (pointer lock required)' : 'headless');
    console.log('  canvas:', `${canvasState.width}x${canvasState.height}`);
    console.log('  mic calls (getUserMedia/enumerateDevices):', canvasState.micCalls);
    console.log('  bad network requests:', badRequests.length);
    console.log('  console errors:', consoleErrors.length);
    console.log('  page errors:', meaningfulPageErrors.length);
    console.log('  pointer lock:', pointerLocked ? 'acquired' : 'not acquired (headless limitation unless WEB_BETA_HEADED=1)');
    console.log('  screenshot:', screenshot);

    let failed = false;
    if (canvasState.width <= 0 || canvasState.height <= 0) {
      console.error('FAIL: canvas did not initialize');
      failed = true;
    }
    if (requirePointerLock && !pointerLocked) {
      console.error('FAIL: pointer lock was not acquired in headed mode');
      failed = true;
    }
    if (canvasState.micCalls !== 0) {
      console.error('FAIL: microphone API was touched');
      failed = true;
    }
    if (badRequests.length > 0) {
      console.error('FAIL: localhost/voice request detected:', badRequests.join(' | '));
      failed = true;
    }
    if (meaningfulPageErrors.length > 0) {
      console.error('FAIL: page errors:', meaningfulPageErrors.join(' | '));
      failed = true;
    }
    if (consoleErrors.length > 0) {
      console.error('console error details:');
      for (const line of consoleErrors.slice(0, 10)) console.error('  ', line);
    }
    if (failed) process.exitCode = 1;
    else console.log('PASS: web-beta browser smoke');
  } finally {
    await browser.close();
    server.close();
  }
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
