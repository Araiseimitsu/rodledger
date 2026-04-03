/**
 * ロットを作成日時昇順（同一時刻は id 昇順）で並べ替えた新しい配列を返す。
 * @param {Array<{ id: number, created_at: string }>} lots
 */
export function sortLotsOldestFirst(lots) {
  return lots.slice().sort((left, right) => {
    const leftTime = new Date(left.created_at).getTime();
    const rightTime = new Date(right.created_at).getTime();
    if (leftTime !== rightTime) {
      return leftTime - rightTime;
    }
    return left.id - right.id;
  });
}

/**
 * 並び済み配列の先頭ロット id を文字列で返す。空なら ''。
 * @param {Array<{ id: number }>} lots
 */
export function firstLotIdString(lots) {
  const lot = lots[0];
  return lot ? String(lot.id) : '';
}
