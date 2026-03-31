/** 全角数字・全角句点を半角に寄せたうえで、半角数字と小数点1つのみ残す */
export function sanitizeWeightInputText(raw) {
  const FULLWIDTH_ZERO = 0xff10;
  let normalized = '';
  for (const ch of String(raw)) {
    const code = ch.codePointAt(0);
    if (code >= FULLWIDTH_ZERO && code <= FULLWIDTH_ZERO + 9) {
      normalized += String.fromCharCode(code - FULLWIDTH_ZERO + 0x30);
    } else if (ch === '．') {
      normalized += '.';
    } else {
      normalized += ch;
    }
  }
  let result = '';
  let dotSeen = false;
  for (const ch of normalized) {
    if (ch >= '0' && ch <= '9') {
      result += ch;
      continue;
    }
    if (ch === '.' && !dotSeen) {
      result += ch;
      dotSeen = true;
    }
  }
  return result;
}

/** 入力中の文字列を重量数値に変換（小数点のみ「456.」などは 0 扱いで、表示文字列は上書きしない） */
export function parseWeightInputToNumber(raw) {
  const trimmed = String(raw).trim();
  if (trimmed === '' || trimmed === '.') return 0;
  const parsed = parseFloat(trimmed);
  if (!Number.isFinite(parsed)) return 0;
  return Number(Math.max(0, parsed).toFixed(3));
}

/** 重量モードに入ったときの入力欄初期表示（末尾ゼロは省略） */
export function weightNumberToInputString(weight) {
  if (!Number.isFinite(weight) || weight <= 0) return '';
  const n = Number(Math.max(0, weight).toFixed(3));
  return String(parseFloat(n.toFixed(3)));
}

const ALLOWED_WEIGHT_NAV_KEYS = new Set([
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

/** 半角・全角の句点をそれぞれ1として数える（二重小数点を検出するため） */
function countRawDots(s) {
  let n = 0;
  for (const ch of s) {
    if (ch === '.' || ch === '．') n++;
  }
  return n;
}

/** 挿入される1文字が重量入力として許容か（全角数字・全角句点は許可し、入力後に半角へ寄せる） */
function isAllowedWeightInsertChar(ch) {
  if (ch >= '0' && ch <= '9') return true;
  if (ch === '.' || ch === '．') return true;
  const code = ch.codePointAt(0);
  if (code >= 0xff10 && code <= 0xff19) return true;
  return false;
}

/**
 * 挿入直前にブロック（keydown だけでは環境によっては文字が入るため併用）
 * 貼り付け・ドロップは input 側の sanitize に任せる
 */
export function beforeWeightInput(event) {
  const type = event.inputType;
  if (type === 'insertFromPaste' || type === 'insertFromDrop' || type === 'insertFromYank') return;
  if (
    type === 'deleteContentBackward' ||
    type === 'deleteContentForward' ||
    type === 'deleteByCut' ||
    type === 'deleteByDrag' ||
    type === 'deleteCompositionText'
  ) {
    return;
  }
  if (type === 'historyUndo' || type === 'historyRedo') return;

  if (type === 'insertLineBreak' || type === 'insertParagraph') {
    event.preventDefault();
    return;
  }

  const data = event.data;
  if (data == null) return;

  for (const ch of data) {
    if (!isAllowedWeightInsertChar(ch)) {
      event.preventDefault();
      return;
    }
  }

  const el = event.currentTarget;
  const value = el.value ?? '';
  const start = el.selectionStart ?? 0;
  const end = el.selectionEnd ?? 0;
  const next = value.slice(0, start) + data + value.slice(end);
  if (countRawDots(next) > 1) {
    event.preventDefault();
  }
}

/** 重量入力: 半角数字と小数点1つのみ（貼り付けは sanitizeWeightInputText で整える） */
export function preventWeightHalfWidthKeys(event) {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (ALLOWED_WEIGHT_NAV_KEYS.has(event.key)) return;
  if (event.key.length === 1 && /^\d$/.test(event.key)) return;

  const isDecimalKey = event.key === '.' || event.key === '．' || event.code === 'NumpadDecimal';
  if (isDecimalKey) {
    const el = event.currentTarget;
    const value = el.value ?? '';
    const start = el.selectionStart ?? 0;
    const end = el.selectionEnd ?? 0;
    if (event.code === 'NumpadDecimal' && event.key !== '.' && event.key !== '．') {
      event.preventDefault();
      return;
    }
    const next = value.slice(0, start) + '.' + value.slice(end);
    if (countRawDots(next) <= 1) return;
  }

  event.preventDefault();
}
