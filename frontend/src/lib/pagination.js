/** 検索入力のデバウンス（ms） */
export const SEARCH_DEBOUNCE_MS = 320;

/**
 * 総件数とページサイズから、1-based の最大ページ番号を返す。
 * @param {number} total
 * @param {number} pageSize
 */
export function maxPageIndex(total, pageSize) {
  if (pageSize <= 0) return 1;
  return Math.max(1, Math.ceil(total / pageSize));
}
