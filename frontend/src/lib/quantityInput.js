/** 本数入力欄用: 0 以上の整数のみ（貼り付け時は先頭の整数として解釈） */
export function parseIntegerQuantityInput(raw) {
  const s = String(raw).trim();
  if (s === '') return 0;
  const parsed = parseInt(s, 10);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(parsed, Number.MAX_SAFE_INTEGER));
}

const ALLOWED_QUANTITY_KEYS = new Set([
  'Backspace',
  'Delete',
  'Tab',
  'Escape',
  'Enter',
  'ArrowLeft',
  'ArrowRight',
  'ArrowUp',
  'ArrowDown',
  'Home',
  'End',
]);

/** 本数入力で小数・指数・負号などを打てないようにする */
export function preventQuantityNonIntegerKeys(event) {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (ALLOWED_QUANTITY_KEYS.has(event.key)) return;
  if (event.key.length === 1 && /^\d$/.test(event.key)) return;
  event.preventDefault();
}
