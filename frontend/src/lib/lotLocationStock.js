/**
 * 場所別在庫行のうち、残本または残重量が正のものだけ（出庫元・入庫先候補の共通判定）
 * @param {Array<{ current_quantity: number, current_weight: number }>} rows
 */
export function filterRowsWithStock(rows) {
  return rows.filter(
    (row) => row.current_quantity > 0 || row.current_weight > 0,
  );
}
