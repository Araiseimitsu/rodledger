/**
 * API クライアント
 * インフラストラクチャ層
 */

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(
  /\/$/,
  "",
);
const API_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS || 15000);

function formatUuidBytes(bytes) {
  const hex = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20, 32)}`;
}

export function createIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }

  if (globalThis.crypto?.getRandomValues) {
    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    return formatUuidBytes(bytes);
  }

  const timestamp = Date.now().toString(16).padStart(12, "0").slice(-12);
  const random = Math.random()
    .toString(16)
    .slice(2)
    .padEnd(20, "0")
    .slice(0, 20);
  return `${timestamp.slice(0, 8)}-${timestamp.slice(8, 12)}-4000-8000-${random}`;
}

async function getErrorMessage(res) {
  const contentType = res.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    try {
      const data = await res.json();
      if (typeof data?.detail === "string" && data.detail) return data.detail;
      if (typeof data?.message === "string" && data.message)
        return data.message;
      return JSON.stringify(data);
    } catch {
      // fall through to text/status handling
    }
  }

  try {
    const text = await res.text();
    if (text.trim()) return text;
  } catch {
    // fall through to status handling
  }

  return `API request failed: ${res.status} ${res.statusText}`;
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(
    () => controller.abort(),
    Number.isFinite(API_TIMEOUT_MS) ? API_TIMEOUT_MS : 15000,
  );

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new Error(await getErrorMessage(res));
    }

    return res;
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(
        "API の応答がタイムアウトしました。サーバーの状態を確認してください",
      );
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function requestJson(path, options = {}) {
  const res = await request(path, options);
  return res.json();
}

/**
 * @typedef {Object} Transaction
 * @property {number} id
 * @property {number} material_id
 * @property {number} lot_id
 * @property {'in'|'out'|'return'|'adjust'|'transfer'} type
 * @property {number} quantity
 * @property {number} weight
 * @property {number} unit_price
 * @property {string} created_at
 * @property {string} [memo]
 * @property {string} [location_note]
 * @property {string} [idempotency_key]
 * @property {string} [lot_code]
 * @property {number} [location_id]
 * @property {string} [location_name]
 * @property {number} [location_from_id]
 * @property {number} [location_to_id]
 * @property {string} [location_from_name]
 * @property {string} [location_to_name]
 */

/**
 * @typedef {Object} StockLocation
 * @property {number} id
 * @property {string} name 棚番（1〜299、文字列で保持）
 * @property {number} sort_order
 * @property {string} created_at
 */

/**
 * @typedef {Object} LotLocationStock
 * @property {number} location_id
 * @property {string} location_name
 * @property {number} current_quantity
 * @property {number} current_weight
 */

/**
 * @typedef {Object} LotLocationStocksResponse
 * @property {number} lot_id
 * @property {LotLocationStock[]} items
 */

/**
 * @typedef {Object} Material
 * @property {number} id
 * @property {string} name
 * @property {number} diameter
 * @property {number} length
 * @property {number} density
 * @property {number} weight_per_unit
 */

/**
 * @typedef {Object} MaterialUpdateInput
 * @property {number} [diameter]
 * @property {number} [length]
 * @property {number} [density]
 */

/**
 * @typedef {Object} Lot
 * @property {number} id
 * @property {number} material_id
 * @property {string} lot_code
 * @property {number} unit_price
 * @property {string} created_at
 */

/**
 * @typedef {Object} LotInventorySummary
 * @property {number} lot_id
 * @property {string} lot_code
 * @property {number} unit_price
 * @property {string} created_at
 * @property {number} current_quantity
 * @property {number} current_weight
 * @property {number} current_value
 */

/**
 * @typedef {Object} LotUpdateInput
 * @property {string} [lot_code]
 * @property {number} [unit_price]
 */

/**
 * @typedef {Object} LotCreateInput
 * @property {number} material_id
 * @property {string} lot_code
 * @property {number} unit_price
 */

/**
 * @typedef {Object} DashboardStats
 * @property {Material} material
 * @property {number} total_quantity
 * @property {number} total_effective_quantity
 * @property {number} total_weight
 * @property {number} total_value
 * @property {LotInventorySummary[]} lot_summaries
 * @property {number | null} oldest_available_lot_id
 * @property {Transaction[]} recent_transactions
 */

/**
 * @typedef {Object} PaginatedTransactions
 * @property {Transaction[]} items
 * @property {number} total
 */

/**
 * @typedef {Object} PaginatedLots
 * @property {Lot[]} items
 * @property {number} total
 */

/**
 * @typedef {Object} PaginatedLotSummaries
 * @property {LotInventorySummary[]} items
 * @property {number} total
 */

/**
 * @typedef {Object} TransactionCreateInput
 * @property {number} material_id
 * @property {number} lot_id
 * @property {'in'|'out'|'return'|'adjust'|'transfer'} type
 * @property {number} quantity
 * @property {number} weight
 * @property {number} [unit_price]
 * @property {string} [memo]
 * @property {string} [location_note]
 * @property {string} [idempotency_key]
 * @property {number} [location_id]
 * @property {number} [location_from_id]
 * @property {number} [location_to_id]
 */

/**
 * 保管場所一覧
 * @returns {Promise<StockLocation[]>}
 */
export async function fetchStockLocations() {
  return requestJson("/stock-locations");
}

/**
 * ロットの場所別在庫
 * @param {number} lotId
 * @returns {Promise<LotLocationStocksResponse>}
 */
export async function fetchLotLocationStocks(lotId) {
  return requestJson(`/inventory/lots/${lotId}/location-stocks`);
}

/**
 * ダッシュボード統計取得
 * @returns {Promise<DashboardStats>}
 */
export async function fetchDashboard() {
  return requestJson("/dashboard");
}

/**
 * 材料マスタ更新
 * @param {number} id
 * @param {MaterialUpdateInput} data
 * @returns {Promise<Material>}
 */
export async function updateMaterial(id, data) {
  return requestJson(`/materials/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

/**
 * トランザクション一覧取得（ページング・検索）
 * @param {Object} [params]
 * @param {number} [params.material_id]
 * @param {string} [params.type]
 * @param {string} [params.q] メモ・ロットコード・ID の部分一致
 * @param {number} [params.limit]
 * @param {number} [params.offset]
 * @returns {Promise<PaginatedTransactions>}
 */
export async function fetchTransactions(params = {}) {
  const query = new URLSearchParams();
  if (params.material_id !== undefined && params.material_id !== null) {
    query.set("material_id", String(params.material_id));
  }
  if (params.type) query.set("type", params.type);
  if (params.q != null && String(params.q).trim() !== "") {
    query.set("q", String(params.q).trim());
  }
  if (params.limit !== undefined && params.limit !== null) {
    query.set("limit", String(params.limit));
  }
  if (params.offset !== undefined && params.offset !== null) {
    query.set("offset", String(params.offset));
  }

  const suffix = query.toString() ? `?${query}` : "";
  return requestJson(`/transactions${suffix}`);
}

/**
 * トランザクション作成
 * @param {TransactionCreateInput} data
 * @returns {Promise<Transaction>}
 */
export async function createTransaction(data) {
  return requestJson("/transactions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

/**
 * トランザクション更新
 * @param {number} id
 * @param {Object} data
 * @param {number} [data.quantity]
 * @param {number} [data.weight]
 * @param {string} [data.memo]
 * @returns {Promise<Transaction>}
 */
export async function updateTransaction(id, data) {
  const query = new URLSearchParams();
  if (data.quantity !== undefined) query.set("quantity", String(data.quantity));
  if (data.weight !== undefined) query.set("weight", String(data.weight));
  if (data.memo !== undefined) query.set("memo", data.memo);

  return requestJson(`/transactions/${id}?${query}`, {
    method: "PUT",
  });
}

/**
 * トランザクション削除
 * @param {number} id
 */
export async function deleteTransaction(id) {
  await request(`/transactions/${id}`, {
    method: "DELETE",
  });
}

/**
 * ロット一覧取得（ページング・検索）
 * @param {number} materialId
 * @param {Object} [params]
 * @param {number} [params.limit] 未指定で全件
 * @param {number} [params.offset]
 * @param {string} [params.q] ロットコードの部分一致
 * @returns {Promise<PaginatedLots>}
 */
export async function fetchLots(materialId, params = {}) {
  const query = new URLSearchParams();
  if (params.limit !== undefined && params.limit !== null) {
    query.set("limit", String(params.limit));
  }
  if (params.offset !== undefined && params.offset !== null) {
    query.set("offset", String(params.offset));
  }
  if (params.q != null && String(params.q).trim() !== "") {
    query.set("q", String(params.q).trim());
  }
  const suffix = query.toString() ? `?${query}` : "";
  return requestJson(`/lots/${materialId}${suffix}`);
}

/**
 * ロット別在庫サマリーのページング（ホームのロット一覧）
 * @param {number} materialId
 * @param {Object} [params]
 * @param {number} [params.limit]
 * @param {number} [params.offset]
 * @param {string} [params.q]
 * @param {boolean} [params.nonzero_only]
 * @returns {Promise<PaginatedLotSummaries>}
 */
export async function fetchLotSummariesPage(materialId, params = {}) {
  const query = new URLSearchParams();
  if (params.limit !== undefined && params.limit !== null) {
    query.set("limit", String(params.limit));
  }
  if (params.offset !== undefined && params.offset !== null) {
    query.set("offset", String(params.offset));
  }
  if (params.q != null && String(params.q).trim() !== "") {
    query.set("q", String(params.q).trim());
  }
  if (params.nonzero_only === false) {
    query.set("nonzero_only", "false");
  }
  const suffix = query.toString() ? `?${query}` : "";
  return requestJson(`/inventory/${materialId}/lot-summaries${suffix}`);
}

/**
 * ロット作成
 * @param {LotCreateInput} data
 * @returns {Promise<Lot>}
 */
export async function createLot(data) {
  return requestJson("/lots", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

/**
 * ロットコード・単価の更新（いずれか一方以上を指定）
 * @param {number} id
 * @param {LotUpdateInput} data
 * @returns {Promise<Lot>}
 */
export async function updateLot(id, data) {
  return requestJson(`/lots/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}
