#!/usr/bin/env node
"use strict";

// Transplant only the clean back-view two-layer head from a rejected full-sheet
// iteration onto the accepted body sheet. The donor iteration is rejected for body
// drift, but its isolated back head satisfies the handed asymmetry contract.

const fs = require("fs");
const sharp = require("sharp");
const { PNG } = require("pngjs");

if (process.argv.length !== 5) {
  throw new Error("usage: transplant_back_head.js BASE.png DONOR.png OUTPUT.png");
}

const basePath = process.argv[2];
const donorPath = process.argv[3];
const outputPath = process.argv[4];

async function main() {
  const donor = PNG.sync.read(fs.readFileSync(donorPath));

  // The crop ends above the shoulder/harness system. It contains the complete upper
  // coral crown, cream separation rim, lower plum nape shell and surrounding background.
  const crop = { left: 772, top: 137, width: 306, height: 143 };
  const raw = await sharp(fs.readFileSync(donorPath))
    .extract(crop)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });

  // Estimate the donor's warm background from crop corners and key it out. The head is
  // opaque line art; a soft eight-pixel distance ramp retains antialiased black contours.
  const corner = [
    [0, 0],
    [crop.width - 1, 0],
    [0, crop.height - 1],
    [crop.width - 1, crop.height - 1]
  ];
  const background = [0, 1, 2].map((channel) => {
    const values = corner.map(([x, y]) => raw.data[(y * crop.width + x) * 4 + channel]);
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  });

  for (let y = 0; y < crop.height; y += 1) {
    for (let x = 0; x < crop.width; x += 1) {
      const index = (y * crop.width + x) * 4;
      const dr = raw.data[index] - background[0];
      const dg = raw.data[index + 1] - background[1];
      const db = raw.data[index + 2] - background[2];
      const distance = Math.sqrt(dr * dr + dg * dg + db * db);
      raw.data[index + 3] = Math.max(0, Math.min(255, Math.round((distance - 8) * 31.875)));
    }
  }

  const keyed = await sharp(raw.data, {
    raw: { width: crop.width, height: crop.height, channels: 4 }
  })
    .trim({ background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toBuffer({ resolveWithObject: true });

  // Target envelope: preserve the accepted base's physical-left/image-left termination
  // at x=785 and height, while extending physical-right/image-right to x=1092.
  const target = { left: 785, top: 145, width: 308, height: 137 };
  const registered = await sharp(keyed.data)
    .resize({ width: target.width, height: target.height, fit: "fill", kernel: sharp.kernel.lanczos3 })
    .png()
    .toBuffer();

  const composed = await sharp(fs.readFileSync(basePath))
    .composite([{ input: registered, left: target.left, top: target.top }])
    .png()
    .toBuffer();
  fs.writeFileSync(outputPath, composed);

  const report = {
    base: basePath,
    donor: donorPath,
    output: outputPath,
    donor_full_sheet_status: "REJECTED_BODY_DRIFT; ISOLATED_BACK_HEAD_ONLY",
    donor_crop: crop,
    donor_trimmed_size: [keyed.info.width, keyed.info.height],
    target_envelope: target,
    changed_scope: "third/back view head only; base sheet outside target envelope untouched"
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});

