// Cadrage d'une photo au format passeport (35 × 45 mm), 2026-11-19 : l'image est affichée dans un
// cadre de ce format, l'utilisateur la déplace et l'agrandit, puis la partie visible devient la
// photo envoyée (OUTPUT_WIDTH × OUTPUT_HEIGHT pixels, JPEG).
//
// Module ES pur, sans dépendance : importé par components/photos/PassportPhotoPicker.tsx et testé par
// lib/photos/passport.test.mjs (`node --test`).
//
// Conventions : `image` = taille d'origine de la photo, `frame` = taille du cadre à l'écran,
// `position` = coin haut-gauche de l'image affichée, relatif au cadre (toujours ≤ 0 : l'image
// couvre le cadre en entier, jamais de bord vide).

/**
 * @typedef {{ width: number, height: number }} Size
 * @typedef {{ x: number, y: number }} Point
 */

export const OUTPUT_WIDTH = 700;
export const OUTPUT_HEIGHT = 900;
export const FRAME_RATIO = 35 / 45;
export const MIN_ZOOM = 1;
export const MAX_ZOOM = 4;

/**
 * Échelle à zoom 1 : la plus petite qui couvre tout le cadre.
 * @param {Size} image
 * @param {Size} frame
 */
export function coverScale(image, frame) {
  return Math.max(frame.width / image.width, frame.height / image.height);
}

/**
 * @param {number} zoom
 */
export function clampZoom(zoom) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
}

/**
 * Position bornée : l'image couvre toujours le cadre.
 * @param {Size} image
 * @param {Size} frame
 * @param {number} zoom
 * @param {Point} position
 * @returns {Point}
 */
export function clampPosition(image, frame, zoom, position) {
  const scale = coverScale(image, frame) * clampZoom(zoom);
  const width = image.width * scale;
  const height = image.height * scale;
  return {
    x: Math.min(0, Math.max(frame.width - width, position.x)),
    y: Math.min(0, Math.max(frame.height - height, position.y)),
  };
}

/**
 * Image centrée dans le cadre.
 * @param {Size} image
 * @param {Size} frame
 * @param {number} zoom
 * @returns {Point}
 */
export function centeredPosition(image, frame, zoom) {
  const scale = coverScale(image, frame) * clampZoom(zoom);
  return clampPosition(image, frame, zoom, {
    x: (frame.width - image.width * scale) / 2,
    y: (frame.height - image.height * scale) / 2,
  });
}

/**
 * Nouveau zoom autour du centre du cadre : le point de l'image au centre y reste.
 * @param {Size} image
 * @param {Size} frame
 * @param {number} fromZoom
 * @param {number} toZoom
 * @param {Point} position
 * @returns {Point}
 */
export function positionAfterZoom(image, frame, fromZoom, toZoom, position) {
  const before = coverScale(image, frame) * clampZoom(fromZoom);
  const after = coverScale(image, frame) * clampZoom(toZoom);
  const centerX = frame.width / 2;
  const centerY = frame.height / 2;
  const imageX = (centerX - position.x) / before;
  const imageY = (centerY - position.y) / before;
  return clampPosition(image, frame, toZoom, { x: centerX - imageX * after, y: centerY - imageY * after });
}

/**
 * Partie de l'image d'origine visible dans le cadre : ce qui sera copié dans la photo finale.
 * @param {Size} image
 * @param {Size} frame
 * @param {number} zoom
 * @param {Point} position
 * @returns {{ sx: number, sy: number, sw: number, sh: number }}
 */
export function sourceRect(image, frame, zoom, position) {
  const scale = coverScale(image, frame) * clampZoom(zoom);
  const bounded = clampPosition(image, frame, zoom, position);
  return { sx: -bounded.x / scale, sy: -bounded.y / scale, sw: frame.width / scale, sh: frame.height / scale };
}

/**
 * Initiales d'un nom, pour la vignette sans photo (« Kossi Mensah » → « KM »).
 * @param {string} name
 */
export function initials(name) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const letters = words.length === 1 ? [words[0][0]] : [words[0][0], words[words.length - 1][0]];
  return letters.join("").toUpperCase();
}
