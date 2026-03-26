"""
データベース接続管理
"""
import aiosqlite
from pathlib import Path

DATABASE_PATH = Path(__file__).parent.parent / "data" / "rodledger.db"
SQLITE_TIMEOUT_SECONDS = 30
SQLITE_BUSY_TIMEOUT_MS = 30000


async def get_db() -> aiosqlite.Connection:
    """データベース接続を取得"""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(DATABASE_PATH, timeout=SQLITE_TIMEOUT_SECONDS)
    db.row_factory = aiosqlite.Row
    await db.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    await db.execute("PRAGMA journal_mode = WAL")
    await db.execute("PRAGMA synchronous = NORMAL")
    await db.execute("PRAGMA foreign_keys = ON")
    return db


async def init_db():
    """データベースの初期化"""
    db = await get_db()
    try:
        # materials テーブル
        await db.execute("""
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                diameter REAL NOT NULL,
                length REAL NOT NULL,
                density REAL NOT NULL,
                weight_per_unit REAL NOT NULL
            )
        """)

        # lots テーブル
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id INTEGER NOT NULL,
                lot_code TEXT NOT NULL UNIQUE,
                unit_price REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (material_id) REFERENCES materials(id)
            )
        """)

        # transactions テーブル
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id INTEGER NOT NULL,
                lot_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('in', 'out', 'return', 'adjust')),
                quantity INTEGER NOT NULL,
                weight REAL NOT NULL,
                unit_price REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                memo TEXT,
                idempotency_key TEXT,
                FOREIGN KEY (material_id) REFERENCES materials(id),
                FOREIGN KEY (lot_id) REFERENCES lots(id)
            )
        """)

        await _ensure_transaction_idempotency_key(db)

        await db.commit()

        # デモ用初期データの投入
        await _seed_demo_data(db)
        await _migrate_demo_material_defaults(db)
        await _reconcile_negative_inventory(db)
    finally:
        await db.close()


async def _seed_demo_data(db: aiosqlite.Connection):
    """デモ用初期データ投入"""
    # 既存データ確認
    cursor = await db.execute("SELECT COUNT(*) FROM materials")
    count = (await cursor.fetchone())[0]
    if count > 0:
        return

    # 材料: SUM22
    # φ8.0 × 2500mm の鋼材
    # 密度: 7.9 g/cm³
    # 重量 = π × r² × 長さ × 密度
    # = π × 0.4² × 250 × 7.9 = 992.7 g ≈ 0.993 kg/本
    weight_per_unit = 0.993  # kg/本

    cursor = await db.execute(
        """
        INSERT INTO materials (name, diameter, length, density, weight_per_unit)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("SUM22", 8.0, 2500.0, 7.9, weight_per_unit),
    )
    await db.commit()
    material_id = cursor.lastrowid

    # デモ用ロット
    cursor = await db.execute(
        """
        INSERT INTO lots (material_id, lot_code, unit_price)
        VALUES (?, ?, ?)
        """,
        (material_id, "LOT-SUM22-001", 275.0),
    )
    await db.commit()
    lot_id = cursor.lastrowid

    # デモ用トランザクション（初期在庫）
    await db.execute(
        """
        INSERT INTO transactions (material_id, lot_id, type, quantity, weight, unit_price, memo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (material_id, lot_id, "in", 100, 99.3, 275.0, "初期在庫"),
    )

    await db.commit()


async def _migrate_demo_material_defaults(db: aiosqlite.Connection):
    """旧デモ初期値を現在の既定値へ一度だけ更新する"""
    await db.execute(
        """
        UPDATE materials
        SET density = ?, weight_per_unit = ?
        WHERE name = ? AND diameter = ? AND length = ? AND density = ?
        """,
        (7.9, 0.993, "SUM22", 8.0, 2500.0, 7.85),
    )

    await db.execute(
        """
        UPDATE lots
        SET unit_price = ?
        WHERE lot_code = ? AND unit_price = ?
        """,
        (275.0, "LOT-SUM22-001", 180.0),
    )

    await db.execute(
        """
        UPDATE transactions
        SET unit_price = ?, weight = ?
        WHERE memo = ? AND type = ? AND unit_price = ? AND weight = ?
        """,
        (275.0, 99.3, "初期在庫", "in", 180.0, 98.7),
    )

    await db.commit()


async def _ensure_transaction_idempotency_key(db: aiosqlite.Connection):
    """既存DBに idempotency_key を追加する"""
    cursor = await db.execute("PRAGMA table_info(transactions)")
    columns = await cursor.fetchall()
    has_column = any(column["name"] == "idempotency_key" for column in columns)

    if not has_column:
        await db.execute("ALTER TABLE transactions ADD COLUMN idempotency_key TEXT")

    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_idempotency_key ON transactions(idempotency_key)"
    )


async def _reconcile_negative_inventory(db: aiosqlite.Connection):
    """既存データの負在庫を adjust で補正する"""
    cursor = await db.execute(
        """
        SELECT
            lots.id AS lot_id,
            lots.material_id AS material_id,
            lots.lot_code AS lot_code,
            lots.unit_price AS unit_price,
            COALESCE(SUM(
                CASE
                    WHEN transactions.type IN ('in', 'return', 'adjust') THEN transactions.quantity
                    WHEN transactions.type = 'out' THEN -transactions.quantity
                    ELSE 0
                END
            ), 0) AS current_quantity,
            COALESCE(SUM(
                CASE
                    WHEN transactions.type IN ('in', 'return', 'adjust') THEN transactions.weight
                    WHEN transactions.type = 'out' THEN -transactions.weight
                    ELSE 0
                END
            ), 0) AS current_weight
        FROM lots
        LEFT JOIN transactions ON transactions.lot_id = lots.id
        GROUP BY lots.id, lots.material_id, lots.lot_code, lots.unit_price
        HAVING current_quantity < 0 OR current_weight < 0
        """
    )
    rows = await cursor.fetchall()

    for row in rows:
        adjust_quantity = max(0, -(row["current_quantity"] or 0))
        adjust_weight = round(max(0.0, -(row["current_weight"] or 0.0)), 3)
        if adjust_quantity == 0 and adjust_weight == 0:
            continue

        idempotency_key = (
            f"auto-adjust-negative-lot:{row['lot_id']}:{adjust_quantity}:{adjust_weight:.3f}"
        )
        memo = f"自動補正: 負在庫解消 {row['lot_code']}"

        await db.execute(
            """
            INSERT OR IGNORE INTO transactions (
                material_id,
                lot_id,
                type,
                quantity,
                weight,
                unit_price,
                memo,
                idempotency_key
            ) VALUES (?, ?, 'adjust', ?, ?, ?, ?, ?)
            """,
            (
                row["material_id"],
                row["lot_id"],
                adjust_quantity,
                adjust_weight,
                row["unit_price"],
                memo,
                idempotency_key,
            ),
        )

    await db.commit()
