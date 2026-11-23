// Tests du cadrage passeport (`node --test`).
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  FRAME_RATIO,
  centeredPosition,
  clampPosition,
  coverScale,
  initials,
  positionAfterZoom,
  sourceRect,
} from "./passport.mjs";

const FRAME = { width: 350, height: 450 };
const close = (actual, expected, label) => assert.ok(Math.abs(actual - expected) < 1e-6, `${label} : ${actual} ≠ ${expected}`);

test("l'image couvre le cadre à zoom 1, quel que soit son format", () => {
  close(coverScale({ width: 1000, height: 1000 }, FRAME), 0.45, "carrée");
  close(coverScale({ width: 4000, height: 3000 }, FRAME), 0.15, "paysage");
  close(coverScale({ width: 3000, height: 4000 }, FRAME), 350 / 3000, "portrait");
});

test("centrée, la partie copiée garde le format 35 × 45 et reste dans l'image", () => {
  for (const image of [
    { width: 1000, height: 1000 },
    { width: 4000, height: 3000 },
    { width: 3000, height: 4000 },
  ]) {
    for (const zoom of [1, 1.7, 4]) {
      const rect = sourceRect(image, FRAME, zoom, centeredPosition(image, FRAME, zoom));
      close(rect.sw / rect.sh, FRAME_RATIO, `format (${image.width}×${image.height}, zoom ${zoom})`);
      assert.ok(rect.sx >= -1e-9 && rect.sy >= -1e-9, "commence dans l'image");
      assert.ok(rect.sx + rect.sw <= image.width + 1e-6 && rect.sy + rect.sh <= image.height + 1e-6, "finit dans l'image");
      close(rect.sx + rect.sw / 2, image.width / 2, "centre horizontal");
      close(rect.sy + rect.sh / 2, image.height / 2, "centre vertical");
    }
  }
});

test("un déplacement trop grand est borné : jamais de bord vide", () => {
  const image = { width: 1000, height: 1000 };
  assert.deepEqual(clampPosition(image, FRAME, 1, { x: 200, y: 200 }), { x: 0, y: 0 });
  assert.deepEqual(clampPosition(image, FRAME, 1, { x: -5000, y: -5000 }), { x: -100, y: 0 });
  const rect = sourceRect(image, FRAME, 1, { x: -5000, y: -5000 });
  close(rect.sx + rect.sw, 1000, "bord droit de l'image");
});

test("zoomer garde au centre du cadre le même point de l'image", () => {
  const image = { width: 3000, height: 4000 };
  const start = centeredPosition(image, FRAME, 1);
  const zoomed = positionAfterZoom(image, FRAME, 1, 2.5, start);
  const before = sourceRect(image, FRAME, 1, start);
  const after = sourceRect(image, FRAME, 2.5, zoomed);
  close(after.sx + after.sw / 2, before.sx + before.sw / 2, "centre horizontal");
  close(after.sy + after.sh / 2, before.sy + before.sh / 2, "centre vertical");
  close(after.sw, before.sw / 2.5, "largeur divisée par le zoom");
});

test("initiales pour la vignette sans photo", () => {
  assert.equal(initials("Kossi Mensah"), "KM");
  assert.equal(initials("  ama  "), "A");
  assert.equal(initials("Yao Kodjo Agbeko"), "YA");
  assert.equal(initials(""), "?");
});
