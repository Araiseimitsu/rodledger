/** 入庫・出庫・移動などで最後に選んだ置き場をブラウザに保持し、次回以降の初期選択に使う */

const STORAGE_KEY = 'rodledger:lastStockLocationId';

/** @param {string[]} a @param {string[]} b */
export function sameStringArray(a, b) {
  if (a.length !== b.length) return false;
  return a.every((v, i) => v === b[i]);
}

export function readLastStockLocationId() {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw == null) return null;
    const n = Number.parseInt(raw, 10);
    if (!Number.isFinite(n) || n <= 0) return null;
    return n;
  } catch {
    return null;
  }
}

/** @param {number | string | null | undefined} id */
export function writeLastStockLocationId(id) {
  if (typeof window === 'undefined') return;
  const n = Number(id);
  if (!Number.isFinite(n) || n <= 0) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, String(n));
  } catch {
    // 容量・プライベートモード等
  }
}
