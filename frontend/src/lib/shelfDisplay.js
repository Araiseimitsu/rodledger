/** 棚番（1〜299）の表示ラベル */
export function formatShelfLabel(shelfNumber) {
  return `棚番 ${shelfNumber}`;
}

export const SHELF_NUMBER_MIN = 1;
export const SHELF_NUMBER_MAX = 299;

/** 棚番の総数（1〜299） */
export const SHELF_COUNT = SHELF_NUMBER_MAX - SHELF_NUMBER_MIN + 1;

/** @param {string} text */
export function parseShelfNumber(text) {
  const n = Number.parseInt(String(text).trim(), 10);
  if (!Number.isFinite(n)) return null;
  if (n < SHELF_NUMBER_MIN || n > SHELF_NUMBER_MAX) return null;
  return n;
}
