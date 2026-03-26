/**
 * API クライアント
 * インフラストラクチャ層
 */

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

async function getErrorMessage(res) {
  const contentType = res.headers.get('content-type') || '';

  if (contentType.includes('application/json')) {
    try {
      const data = await res.json();
      if (typeof data?.detail === 'string' && data.detail) return data.detail;
      if (typeof data?.message === 'string' && data.message) return data.message;
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
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    throw new Error(await getErrorMessage(res));
  }
  return res;
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
 * @property {'in'|'out'|'return'|'adjust'} type
 * @property {number} quantity
 * @property {number} weight
 * @property {number} unit_price
 * @property {string} created_at
 * @property {string} [memo]
 * @property {string} [idempotency_key]
 * @property {string} [lot_code]
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
 * @property {number} unit_price
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
 * @property {number} total_weight
 * @property {number} total_value
 * @property {LotInventorySummary[]} lot_summaries
 * @property {number | null} oldest_available_lot_id
 * @property {Transaction[]} recent_transactions
 */

/**
 * @typedef {Object} TransactionCreateInput
 * @property {number} material_id
 * @property {number} lot_id
 * @property {'in'|'out'|'return'|'adjust'} type
 * @property {number} quantity
 * @property {number} weight
 * @property {number} [unit_price]
 * @property {string} [memo]
 * @property {string} [idempotency_key]
 */

/**
 * ダッシュボード統計取得
 * @returns {Promise<DashboardStats>}
 */
export async function fetchDashboard() {
  return requestJson('/dashboard');
}

/**
 * 材料マスタ更新
 * @param {number} id
 * @param {MaterialUpdateInput} data
 * @returns {Promise<Material>}
 */
export async function updateMaterial(id, data) {
  return requestJson(`/materials/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

/**
 * トランザクション一覧取得
 * @param {Object} [params]
 * @param {number} [params.material_id]
 * @param {string} [params.type]
 * @param {number} [params.limit]
 * @returns {Promise<Transaction[]>}
 */
export async function fetchTransactions(params = {}) {
  const query = new URLSearchParams();
  if (params.material_id !== undefined && params.material_id !== null) {
    query.set('material_id', String(params.material_id));
  }
  if (params.type) query.set('type', params.type);
  if (params.limit !== undefined && params.limit !== null) {
    query.set('limit', String(params.limit));
  }
  if (params.offset !== undefined && params.offset !== null) {
    query.set('offset', String(params.offset));
  }

  const suffix = query.toString() ? `?${query}` : '';
  return requestJson(`/transactions${suffix}`);
}

/**
 * トランザクション作成
 * @param {TransactionCreateInput} data
 * @returns {Promise<Transaction>}
 */
export async function createTransaction(data) {
  return requestJson('/transactions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
  if (data.quantity !== undefined) query.set('quantity', String(data.quantity));
  if (data.weight !== undefined) query.set('weight', String(data.weight));
  if (data.memo !== undefined) query.set('memo', data.memo);

  return requestJson(`/transactions/${id}?${query}`, {
    method: 'PUT',
  });
}

/**
 * トランザクション削除
 * @param {number} id
 */
export async function deleteTransaction(id) {
  await request(`/transactions/${id}`, {
    method: 'DELETE',
  });
}

/**
 * ロット一覧取得
 * @param {number} materialId
 * @returns {Promise<Lot[]>}
 */
export async function fetchLots(materialId) {
  return requestJson(`/lots/${materialId}`);
}

/**
 * ロット作成
 * @param {LotCreateInput} data
 * @returns {Promise<Lot>}
 */
export async function createLot(data) {
  return requestJson('/lots', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

/**
 * ロット単価更新
 * @param {number} id
 * @param {LotUpdateInput} data
 * @returns {Promise<Lot>}
 */
export async function updateLot(id, data) {
  return requestJson(`/lots/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}
