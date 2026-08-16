#!/usr/bin/env node
"use strict";

// Deterministic local registration for Mira's physical-right rear head lobe.
// The accepted generated sheet already resolves the two-layer head in every view, but
// its back projection remains 4 px shorter on physical right.  This script stretches
// only the right half of the back head assembly; all pixels outside the recorded head
// ROI are copied byte-for-byte from the input.

const fs = require("fs");
const { PNG } = require("pngjs");
const sharp = require("sharp");

if (process.argv.length !== 4) {
  throw new Error("usage: register_back_lobe.js INPUT.png OUTPUT.png");
}

const inputPath = process.argv[2];
const outputPath = process.argv[3];
const input = PNG.sync.read(fs.readFileSync(inputPath));
const output = PNG.sync.read(fs.readFileSync(inputPath));

const centerX = 932;
const sourceRight = 1076;
const targetRight = 1092;
const minY = 140;
const maxY = 268;
const scaleX = (targetRight - centerX) / (sourceRight - centerX);

function offset(x, y) {
  return (y * input.width + x) * 4;
}

function isHeadMaterial(x, y) {
  if (x < centerX || x > sourceRight || y < minY || y > maxY) return false;
  const i = offset(x, y);
  const r = input.data[i];
  const g = input.data[i + 1];
  const b = input.data[i + 2];

  const coral = r >= 112 && r - g >= 18 && g - b >= 2;
  const cream = r >= 130 && g >= 82 && r - b >= 30 && g - b >= 18;
  const plum = r >= 47 && r <= 126 && b >= g && r - g >= 8;
  return coral || cream || plum;
}

// Include the thin dark ink boundary immediately adjoining selected head material, but
// never the diagonal harness.  A two-pixel neighborhood is enough for the source line.
function isSelected(x, y) {
  if (isHeadMaterial(x, y)) return true;
  if (x < centerX || x > sourceRight || y < minY || y > maxY) return false;
  const i = offset(x, y);
  const r = input.data[i];
  const g = input.data[i + 1];
  const b = input.data[i + 2];
  const darkInk = Math.max(r, g, b) <= 72;
  if (!darkInk) return false;
  for (let dy = -2; dy <= 2; dy += 1) {
    for (let dx = -2; dx <= 2; dx += 1) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx >= 0 && nx < input.width && ny >= 0 && ny < input.height && isHeadMaterial(nx, ny)) {
        return true;
      }
    }
  }
  return false;
}

async function main() {
  const sourceWidth = sourceRight - centerX + 1;
  const sourceHeight = maxY - minY + 1;
  const targetWidth = targetRight - centerX + 1;
  const cutout = new PNG({ width: sourceWidth, height: sourceHeight });

  // Build a transparent head-only cutout. Lanczos resizing of RGBA preserves a smooth
  // antialiased contour without bleeding the warm background into the shell edge.
  for (let y = minY; y <= maxY; y += 1) {
    for (let x = centerX; x <= sourceRight; x += 1) {
      if (!isSelected(x, y)) continue;
      const sourceIndex = offset(x, y);
      const localIndex = ((y - minY) * sourceWidth + (x - centerX)) * 4;
      for (let channel = 0; channel < 4; channel += 1) {
        cutout.data[localIndex + channel] = input.data[sourceIndex + channel];
      }
      cutout.data[localIndex + 3] = input.data[sourceIndex + 3];
    }
  }

  const resized = await sharp(PNG.sync.write(cutout))
    .resize({ width: targetWidth, height: sourceHeight, kernel: sharp.kernel.lanczos3 })
    .png()
    .toBuffer();

  const composed = await sharp(PNG.sync.write(output))
    .composite([{ input: resized, left: centerX, top: minY }])
    .png()
    .toBuffer();
  fs.writeFileSync(outputPath, composed);

  const report = {
  input: inputPath,
  output: outputPath,
  untouched_outside_roi: [centerX, minY, targetRight, maxY],
  center_x: centerX,
  source_right_x: sourceRight,
  target_right_x: targetRight,
  x_scale_ratio: scaleX,
  changed_scope: "back-view physical-right upper-crown/lower-nape head material and adjacent ink only"
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
