"""
データベース接続管理
"""
import aiosqlite
from pathlib import Path

from app.models.models import SHELF_NUMBER_MAX, SHELF_NUMBER_MIN

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

        # lots テーブル（材料ごとにロットコードは一意）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id INTEGER NOT NULL,
                lot_code TEXT NOT NULL,
                unit_price REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (material_id) REFERENCES materials(id),
                UNIQUE (material_id, lot_code)
            )
        """)

        # 保管場所マスタ（transactions より先に作成）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stock_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # transactions テーブル（新規 DB 用。既存レガシーは _migrate_legacy_transactions_table で置換）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id INTEGER NOT NULL,
                lot_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('in', 'out', 'return', 'adjust', 'transfer')),
                quantity INTEGER NOT NULL,
                weight REAL NOT NULL,
                unit_price REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                memo TEXT,
                idempotency_key TEXT,
                location_id INTEGER,
                location_from_id INTEGER,
                location_to_id INTEGER,
                FOREIGN KEY (material_id) REFERENCES materials(id),
                FOREIGN KEY (lot_id) REFERENCES lots(id),
                FOREIGN KEY (location_id) REFERENCES stock_locations(id),
                FOREIGN KEY (location_from_id) REFERENCES stock_locations(id),
                FOREIGN KEY (location_to_id) REFERENCES stock_locations(id)
            )
        """)

        await _ensure_transaction_idempotency_key(db)
        await _ensure_all_shelf_numbers_seeded(db)
        await _migrate_legacy_transactions_table(db)
        await _migrate_stock_locations_legacy_names(db)
        await _migrate_lots_unique_per_material(db)

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

    cursor = await db.execute(
        "SELECT id FROM stock_locations WHERE name = ?", ("1",)
    )
    loc_row = await cursor.fetchone()
    if not loc_row:
        raise RuntimeError("棚番1の stock_locations が見つかりません")
    default_location_id = int(loc_row["id"])

    # デモ用トランザクション（初期在庫）
    await db.execute(
        """
        INSERT INTO transactions (
            material_id, lot_id, type, quantity, weight, unit_price, memo, location_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (material_id, lot_id, "in", 100, 99.3, 275.0, "初期在庫", default_location_id),
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


async def _ensure_all_shelf_numbers_seeded(db: aiosqlite.Connection):
    """
    棚番 SHELF_NUMBER_MIN〜SHELF_NUMBER_MAX をすべて登録する（既存は INSERT OR IGNORE でスキップ）。
    置き場は常に全棚分存在する前提。
    """
    rows = [
        (str(n), n) for n in range(SHELF_NUMBER_MIN, SHELF_NUMBER_MAX + 1)
    ]
    await db.executemany(
        """
        INSERT OR IGNORE INTO stock_locations (name, sort_order)
        VALUES (?, ?)
        """,
        rows,
    )


async def _migrate_stock_locations_legacy_names(db: aiosqlite.Connection):
    """
    旧データの「未設定」を棚番1へ寄せる。
    既に棚番1がある場合は参照を統合して重複行を削除する。
    """
    cursor = await db.execute(
        "SELECT id FROM stock_locations WHERE name = ?", ("未設定",)
    )
    unset_row = await cursor.fetchone()
    if not unset_row:
        return
    unset_id = int(unset_row["id"])

    cursor = await db.execute(
        "SELECT id FROM stock_locations WHERE name = ?", ("1",)
    )
    one_row = await cursor.fetchone()

    if one_row and int(one_row["id"]) != unset_id:
        one_id = int(one_row["id"])
        for col in ("location_id", "location_from_id", "location_to_id"):
            await db.execute(
                f"UPDATE transactions SET {col} = ? WHERE {col} = ?",
                (one_id, unset_id),
            )
        await db.execute("DELETE FROM stock_locations WHERE id = ?", (unset_id,))
    else:
        await db.execute(
            """
            UPDATE stock_locations
            SET name = '1', sort_order = 1
            WHERE id = ?
            """,
            (unset_id,),
        )


def _should_migrate_lots_to_material_scoped_lot_code(table_sql: str | None) -> bool:
    """CREATE TABLE lots が旧スキーマ（lot_code 単独 UNIQUE）かどうか。"""
    if not table_sql:
        return False
    compact = table_sql.replace(" ", "").replace("\n", "").lower()
    if "unique(material_id,lot_code)" in compact:
        return False
    return "lot_codetextnotnullunique" in compact


async def _migrate_lots_unique_per_material(db: aiosqlite.Connection) -> None:
    """
    lots.lot_code のグローバル UNIQUE を廃止し、材料単位の UNIQUE(material_id, lot_code) に変更する。
    """
    cursor = await db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='lots'"
    )
    row = await cursor.fetchone()
    if not row or not _should_migrate_lots_to_material_scoped_lot_code(row["sql"]):
        return

    # 未コミットのトランザクション内では PRAGMA foreign_keys=OFF が no-op になり、
    # DROP TABLE lots が transactions からの FK で失敗するため、先に確定する。
    await db.commit()
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """
            CREATE TABLE lots_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id INTEGER NOT NULL,
                lot_code TEXT NOT NULL,
                unit_price REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (material_id) REFERENCES materials(id),
                UNIQUE (material_id, lot_code)
            )
            """
        )
        await db.execute("INSERT INTO lots_new SELECT * FROM lots")
        await db.execute("DROP TABLE lots")
        await db.execute("ALTER TABLE lots_new RENAME TO lots")

        cursor = await db.execute("SELECT MAX(id) AS m FROM lots")
        max_row = await cursor.fetchone()
        max_id = max_row["m"] if max_row and max_row["m"] is not None else 0
        if max_id > 0:
            await db.execute("DELETE FROM sqlite_sequence WHERE name = 'lots'")
            await db.execute(
                "INSERT INTO sqlite_sequence (name, seq) VALUES ('lots', ?)",
                (max_id,),
            )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")


async def _get_default_stock_location_id(db: aiosqlite.Connection) -> int:
    await _ensure_all_shelf_numbers_seeded(db)
    cursor = await db.execute(
        "SELECT id FROM stock_locations WHERE name = ?", ("1",)
    )
    row = await cursor.fetchone()
    if not row:
        raise RuntimeError("棚番1の stock_locations が見つかりません")
    return int(row["id"])


async def _migrate_legacy_transactions_table(db: aiosqlite.Connection):
    """
    旧スキーマの transactions（location 列なし）を新スキーマへ移行する。
    新規作成済みの場合は何もしない。
    """
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'"
    )
    if not await cursor.fetchone():
        return

    cursor = await db.execute("PRAGMA table_info(transactions)")
    columns = {col["name"] for col in await cursor.fetchall()}
    if "location_id" in columns:
        return

    await _ensure_all_shelf_numbers_seeded(db)
    default_location_id = await _get_default_stock_location_id(db)

    await db.execute(
        """
        CREATE TABLE transactions_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            lot_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('in', 'out', 'return', 'adjust', 'transfer')),
            quantity INTEGER NOT NULL,
            weight REAL NOT NULL,
            unit_price REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            memo TEXT,
            idempotency_key TEXT,
            location_id INTEGER,
            location_from_id INTEGER,
            location_to_id INTEGER,
            FOREIGN KEY (material_id) REFERENCES materials(id),
            FOREIGN KEY (lot_id) REFERENCES lots(id),
            FOREIGN KEY (location_id) REFERENCES stock_locations(id),
            FOREIGN KEY (location_from_id) REFERENCES stock_locations(id),
            FOREIGN KEY (location_to_id) REFERENCES stock_locations(id)
        )
        """
    )

    await db.execute(
        f"""
        INSERT INTO transactions_new (
            id, material_id, lot_id, type, quantity, weight, unit_price,
            created_at, memo, idempotency_key, location_id, location_from_id, location_to_id
        )
        SELECT
            id, material_id, lot_id, type, quantity, weight, unit_price,
            created_at, memo, idempotency_key,
            {default_location_id}, NULL, NULL
        FROM transactions
        """
    )

    await db.execute("DROP TABLE transactions")
    await db.execute("ALTER TABLE transactions_new RENAME TO transactions")

    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_idempotency_key ON transactions(idempotency_key)"
    )

    cursor = await db.execute("SELECT MAX(id) AS m FROM transactions")
    max_row = await cursor.fetchone()
    max_id = max_row["m"] if max_row and max_row["m"] is not None else 0
    if max_id > 0:
        await db.execute(
            "DELETE FROM sqlite_sequence WHERE name = 'transactions'"
        )
        await db.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES ('transactions', ?)",
            (max_id,),
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
