"""
在庫計算サービス
"""
import logging
import math
from typing import Optional
import sqlite3

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models.models import (
    Material,
    MaterialUpdate,
    Lot,
    LotCreate,
    LotUpdate,
    LotInventorySummary,
    LotLocationStock,
    StockLocation,
    StockLocationCreate,
    StockLocationUpdate,
    Transaction,
    TransactionCreate,
    TransactionType,
    InventorySummary,
    DashboardStats,
)


class InsufficientInventoryError(Exception):
    """在庫不足を表す例外"""


class InsufficientLocationInventoryError(Exception):
    """指定場所の在庫不足を表す例外"""


class InventoryService:
    """在庫計算ロジック"""

    # 重量は 0.001kg 単位で表示・積み上げるため、本数×単重の換算値が残重量をわずかに超えることがある
    _OUTBOUND_WEIGHT_TOLERANCE_KG = 0.001

    @staticmethod
    def _unit_prices_equal(a: float, b: float) -> bool:
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)

    @staticmethod
    async def _merge_create_with_existing_lot(
        existing: Lot, requested_unit_price: float
    ) -> Lot:
        """POST /lots で同一材料・同一コードが既にある場合の単価マージ"""
        if InventoryService._unit_prices_equal(
            existing.unit_price, requested_unit_price
        ):
            return existing
        updated = await InventoryService.update_lot(
            existing.id, LotUpdate(unit_price=requested_unit_price)
        )
        if updated is not None:
            return updated
        return existing

    @staticmethod
    async def _get_default_location_id() -> int:
        """既定の保管場所 ID（棚番1）"""
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT id FROM stock_locations WHERE name = ?", ("1",)
            )
            row = await cursor.fetchone()
            if not row:
                raise RuntimeError("棚番1の stock_locations が見つかりません")
            return int(row["id"])
        finally:
            await db.close()

    @staticmethod
    async def list_stock_locations() -> list[StockLocation]:
        """保管場所一覧（表示順）"""
        db = await get_db()
        try:
            cursor = await db.execute(
                """
                SELECT * FROM stock_locations
                ORDER BY sort_order ASC, id ASC
                """
            )
            rows = await cursor.fetchall()
            return [StockLocation(**dict(row)) for row in rows]
        finally:
            await db.close()

    @staticmethod
    async def create_stock_location(data: StockLocationCreate) -> StockLocation:
        """保管場所を追加（棚番1〜299は起動時に全件登録済みのため不可）"""
        raise ValueError(
            "棚番1〜299はデータベース起動時にすべて登録済みです。新規追加は不要です。"
        )

    @staticmethod
    async def update_stock_location(
        location_id: int, data: StockLocationUpdate
    ) -> Optional[StockLocation]:
        """表示順のみ更新可（棚番の変更は不可）"""
        existing = await InventoryService.get_stock_location(location_id)
        if not existing:
            return None

        if data.name is not None and data.name != existing.name:
            raise ValueError(
                "棚番の変更はできません。一覧の並び替えが必要な場合のみ表示順を更新してください。"
            )

        next_order = (
            data.sort_order if data.sort_order is not None else existing.sort_order
        )

        db = await get_db()
        try:
            await db.execute(
                """
                UPDATE stock_locations
                SET sort_order = ?
                WHERE id = ?
                """,
                (next_order, location_id),
            )
            await db.commit()
        finally:
            await db.close()

        return await InventoryService.get_stock_location(location_id)

    @staticmethod
    async def count_transactions_referencing_location(location_id: int) -> int:
        """取引がこの保管場所を参照している件数"""
        db = await get_db()
        try:
            cursor = await db.execute(
                """
                SELECT COUNT(*) AS c FROM transactions
                WHERE location_id = ?
                   OR location_from_id = ?
                   OR location_to_id = ?
                """,
                (location_id, location_id, location_id),
            )
            row = await cursor.fetchone()
            return int(row["c"]) if row else 0
        finally:
            await db.close()

    @staticmethod
    async def delete_stock_location(location_id: int) -> bool:
        """保管場所を削除（棚番1〜299はマスタ固定のため不可）"""
        raise ValueError("棚番1〜299はマスタ固定のため削除できません")

    @staticmethod
    async def get_stock_location(location_id: int) -> Optional[StockLocation]:
        """保管場所を1件取得"""
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM stock_locations WHERE id = ?", (location_id,)
            )
            row = await cursor.fetchone()
            if row:
                return StockLocation(**dict(row))
            return None
        finally:
            await db.close()

    @staticmethod
    async def get_lot_location_stocks(lot_id: int) -> list[LotLocationStock]:
        """ロットの場所別残（履歴から集計）"""
        db = await get_db()
        try:
            cursor = await db.execute(
                """
                SELECT
                    sl.id AS location_id,
                    sl.name AS location_name,
                    COALESCE(SUM(
                        CASE
                            WHEN t.type IN ('in', 'return', 'adjust')
                                AND t.location_id = sl.id
                                THEN t.quantity
                            WHEN t.type = 'out' AND t.location_id = sl.id
                                THEN -t.quantity
                            WHEN t.type = 'transfer' AND t.location_from_id = sl.id
                                THEN -t.quantity
                            WHEN t.type = 'transfer' AND t.location_to_id = sl.id
                                THEN t.quantity
                            ELSE 0
                        END
                    ), 0) AS current_quantity,
                    COALESCE(SUM(
                        CASE
                            WHEN t.type IN ('in', 'return', 'adjust')
                                AND t.location_id = sl.id
                                THEN t.weight
                            WHEN t.type = 'out' AND t.location_id = sl.id
                                THEN -t.weight
                            WHEN t.type = 'transfer' AND t.location_from_id = sl.id
                                THEN -t.weight
                            WHEN t.type = 'transfer' AND t.location_to_id = sl.id
                                THEN t.weight
                            ELSE 0
                        END
                    ), 0) AS current_weight
                FROM stock_locations sl
                LEFT JOIN transactions t
                    ON t.lot_id = ?
                    AND (
                        (t.type IN ('in', 'return', 'adjust', 'out') AND t.location_id = sl.id)
                        OR (
                            t.type = 'transfer'
                            AND (t.location_from_id = sl.id OR t.location_to_id = sl.id)
                        )
                    )
                GROUP BY sl.id, sl.name
                HAVING current_quantity != 0 OR current_weight != 0
                ORDER BY sl.sort_order ASC, sl.id ASC
                """,
                (lot_id,),
            )
            rows = await cursor.fetchall()
            return [
                LotLocationStock(
                    location_id=row["location_id"],
                    location_name=row["location_name"],
                    current_quantity=int(row["current_quantity"] or 0),
                    current_weight=InventoryService._normalize_zero(
                        float(row["current_weight"] or 0.0), 3
                    ),
                )
                for row in rows
            ]
        finally:
            await db.close()

    @staticmethod
    async def _get_lot_location_balance(
        db,
        lot_id: int,
        location_id: int,
    ) -> tuple[int, float]:
        """ロット×場所の残本数・残重量"""
        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(
                    CASE
                        WHEN type IN ('in', 'return', 'adjust') AND transactions.location_id = ?
                            THEN quantity
                        WHEN type = 'out' AND transactions.location_id = ?
                            THEN -quantity
                        WHEN type = 'transfer' AND transactions.location_from_id = ?
                            THEN -quantity
                        WHEN type = 'transfer' AND transactions.location_to_id = ?
                            THEN quantity
                        ELSE 0
                    END
                ), 0) AS q,
                COALESCE(SUM(
                    CASE
                        WHEN type IN ('in', 'return', 'adjust') AND transactions.location_id = ?
                            THEN weight
                        WHEN type = 'out' AND transactions.location_id = ?
                            THEN -weight
                        WHEN type = 'transfer' AND transactions.location_from_id = ?
                            THEN -weight
                        WHEN type = 'transfer' AND transactions.location_to_id = ?
                            THEN weight
                        ELSE 0
                    END
                ), 0) AS w
            FROM transactions
            WHERE lot_id = ?
            """,
            (
                location_id,
                location_id,
                location_id,
                location_id,
                location_id,
                location_id,
                location_id,
                location_id,
                lot_id,
            ),
        )
        row = await cursor.fetchone()
        if not row:
            return 0, 0.0
        qty = int(row["q"] or 0)
        w = InventoryService._normalize_zero(float(row["w"] or 0.0), 3)
        return qty, w

    @staticmethod
    def _normalize_zero(value: float, digits: int = 3) -> float:
        """丸め後の -0.0 を 0.0 に正規化する"""
        rounded = round(value, digits)
        return 0.0 if rounded == 0 else rounded

    @staticmethod
    def _quantity_from_weight_like_frontend(weight: float, weight_per_unit: float) -> int:
        """
        フロントの calculateQuantityFromWeight（normalizeWeight + Math.round）に揃えた本数換算。
        Python の round と JS の Math.round の差を避けるため、非負実数では floor(x+0.5) を使う。
        """
        if weight_per_unit <= 0 or not math.isfinite(weight_per_unit):
            return 0
        w = InventoryService._normalize_zero(max(0.0, weight), 3)
        ratio = w / weight_per_unit
        if not math.isfinite(ratio):
            return 0
        return max(0, int(math.floor(ratio + 0.5)))

    @staticmethod
    def _outbound_weight_within_stock(request_weight: float, stock_weight: float) -> bool:
        """出庫重量が在庫重量以内か（積み上げ丸めと換算の差を許容）"""
        rq = InventoryService._normalize_zero(max(0.0, request_weight), 3)
        sq = InventoryService._normalize_zero(max(0.0, stock_weight), 3)
        return rq <= sq + InventoryService._OUTBOUND_WEIGHT_TOLERANCE_KG + 1e-9

    @staticmethod
    def _effective_stock_quantity(
        quantity: int,
        weight: float,
        weight_per_unit: float,
    ) -> int:
        """
        本数と重量を別々に積み上げた結果の丸め誤差で、片方だけゼロ付近に残るケースを実質在庫なしにまとめる。
        """
        if weight_per_unit <= 0 or not math.isfinite(weight_per_unit):
            return quantity if quantity > 0 else (1 if weight > 0 else 0)
        return max(quantity, InventoryService._quantity_from_weight_like_frontend(weight, weight_per_unit))

    @staticmethod
    def _total_effective_quantity(
        lot_summaries: list[LotInventorySummary],
        weight_per_unit: float,
    ) -> int:
        """ロット別の実効本数（帳簿本数と重量換算の大きい方）の合計"""
        return sum(
            InventoryService._effective_stock_quantity(
                lot.current_quantity,
                lot.current_weight,
                weight_per_unit,
            )
            for lot in lot_summaries
        )

    @staticmethod
    def _normalize_lot_summary_for_display(
        summary: LotInventorySummary,
        weight_per_unit: float,
    ) -> LotInventorySummary:
        """実効在庫ゼロのロットは表示・集計から除外する（本数・重量・金額を 0 に正規化）"""
        if InventoryService._effective_stock_quantity(
            summary.current_quantity,
            summary.current_weight,
            weight_per_unit,
        ) > 0:
            return summary
        return LotInventorySummary(
            lot_id=summary.lot_id,
            lot_code=summary.lot_code,
            unit_price=summary.unit_price,
            created_at=summary.created_at,
            current_quantity=0,
            current_weight=0.0,
            current_value=0.0,
        )

    @staticmethod
    async def _get_lot_inventory_summaries(
        db,
        material_id: int,
    ) -> list[LotInventorySummary]:
        """材料に紐づくロット別在庫を作成日時昇順で集計する"""
        cursor = await db.execute(
            """
            SELECT
                lots.id AS lot_id,
                lots.lot_code AS lot_code,
                lots.unit_price AS unit_price,
                lots.created_at AS created_at,
                COALESCE(SUM(
                    CASE
                        WHEN transactions.type IN ('in', 'return') THEN transactions.quantity
                        WHEN transactions.type = 'out' THEN -transactions.quantity
                        WHEN transactions.type = 'adjust' THEN transactions.quantity
                        ELSE 0
                    END
                ), 0) AS current_quantity,
                COALESCE(SUM(
                    CASE
                        WHEN transactions.type IN ('in', 'return') THEN transactions.weight
                        WHEN transactions.type = 'out' THEN -transactions.weight
                        WHEN transactions.type = 'adjust' THEN transactions.weight
                        ELSE 0
                    END
                ), 0) AS current_weight
            FROM lots
            LEFT JOIN transactions ON transactions.lot_id = lots.id
            WHERE lots.material_id = ?
            GROUP BY lots.id, lots.lot_code, lots.unit_price, lots.created_at
            ORDER BY datetime(lots.created_at) ASC, lots.id ASC
            """,
            (material_id,),
        )
        rows = await cursor.fetchall()
        return [
            LotInventorySummary(
                lot_id=row["lot_id"],
                lot_code=row["lot_code"],
                unit_price=row["unit_price"],
                created_at=row["created_at"],
                current_quantity=row["current_quantity"] or 0,
                current_weight=InventoryService._normalize_zero(row["current_weight"] or 0.0, 3),
                current_value=InventoryService._normalize_zero((row["current_weight"] or 0.0) * row["unit_price"], 1),
            )
            for row in rows
        ]

    @staticmethod
    def _get_oldest_available_lot_id(
        lot_summaries: list[LotInventorySummary],
    ) -> Optional[int]:
        """在庫のあるロットのうち、作成日時が最も古いものの ID を返す"""
        for lot_summary in lot_summaries:
            if lot_summary.current_quantity > 0 or lot_summary.current_weight > 0:
                return lot_summary.lot_id
        return None

    @staticmethod
    def calculate_weight_per_unit(diameter: float, length: float, density: float) -> float:
        """径(mm)・長さ(mm)・比重(g/cm3)から単重(kg/本)を算出"""
        radius_cm = (diameter / 2) / 10
        length_cm = length / 10
        weight_grams = math.pi * (radius_cm ** 2) * length_cm * density
        return round(weight_grams / 1000, 3)

    @staticmethod
    async def get_material(material_id: int) -> Optional[Material]:
        """材料取得"""
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM materials WHERE id = ?", (material_id,)
            )
            row = await cursor.fetchone()
            if row:
                return Material(**dict(row))
            return None
        finally:
            await db.close()

    @staticmethod
    async def get_all_materials() -> list[Material]:
        """全材料取得"""
        db = await get_db()
        try:
            cursor = await db.execute("SELECT * FROM materials ORDER BY id")
            rows = await cursor.fetchall()
            return [Material(**dict(row)) for row in rows]
        finally:
            await db.close()

    @staticmethod
    async def update_material(material_id: int, data: MaterialUpdate) -> Optional[Material]:
        """材料マスタ更新"""
        material = await InventoryService.get_material(material_id)
        if not material:
            return None

        next_diameter = data.diameter if data.diameter is not None else material.diameter
        next_length = data.length if data.length is not None else material.length
        next_density = data.density if data.density is not None else material.density
        next_weight_per_unit = InventoryService.calculate_weight_per_unit(
            diameter=next_diameter,
            length=next_length,
            density=next_density,
        )

        db = await get_db()
        try:
            await db.execute(
                """
                UPDATE materials
                SET diameter = ?, length = ?, density = ?, weight_per_unit = ?
                WHERE id = ?
                """,
                (
                    next_diameter,
                    next_length,
                    next_density,
                    next_weight_per_unit,
                    material_id,
                ),
            )
            await db.commit()
        finally:
            await db.close()

        return await InventoryService.get_material(material_id)

    @staticmethod
    async def get_lots_by_material(
        material_id: int,
        limit: Optional[int] = None,
        offset: int = 0,
        search: Optional[str] = None,
    ) -> tuple[list[Lot], int]:
        """材料に紐づくロット一覧（件数付き）。limit が None のときは全件。"""
        db = await get_db()
        try:
            where = "material_id = ?"
            params: list = [material_id]
            if search and search.strip():
                where += " AND lot_code LIKE ?"
                params.append(f"%{search.strip()}%")

            cursor = await db.execute(
                f"SELECT COUNT(*) AS c FROM lots WHERE {where}",
                params,
            )
            count_row = await cursor.fetchone()
            total = int(count_row["c"]) if count_row else 0

            if limit is None:
                cursor = await db.execute(
                    f"SELECT * FROM lots WHERE {where} ORDER BY datetime(created_at) DESC",
                    params,
                )
            else:
                cursor = await db.execute(
                    f"""
                    SELECT * FROM lots WHERE {where}
                    ORDER BY datetime(created_at) DESC
                    LIMIT ? OFFSET ?
                    """,
                    params + [limit, offset],
                )
            rows = await cursor.fetchall()
            return [Lot(**dict(row)) for row in rows], total
        finally:
            await db.close()

    @staticmethod
    async def get_lot(lot_id: int) -> Optional[Lot]:
        """ロット取得"""
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM lots WHERE id = ?", (lot_id,)
            )
            row = await cursor.fetchone()
            if row:
                return Lot(**dict(row))
            return None
        finally:
            await db.close()

    @staticmethod
    async def get_lot_by_material_and_code(
        material_id: int, lot_code: str
    ) -> Optional[Lot]:
        """材料 ID とロットコードで検索（同一材料内の一意キー）"""
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM lots WHERE material_id = ? AND lot_code = ?",
                (material_id, lot_code),
            )
            row = await cursor.fetchone()
            if row:
                return Lot(**dict(row))
            return None
        finally:
            await db.close()

    @staticmethod
    async def create_lot(data: LotCreate) -> Lot:
        """
        ロット作成。
        同一材料・同一ロットコードが既にあれば新規行は作らず、既存ロットを返す（入庫の「既存ロット」と同じ扱い）。
        単価だけ異なる場合は既存ロットの単価を更新する。
        """
        existing = await InventoryService.get_lot_by_material_and_code(
            data.material_id, data.lot_code
        )
        if existing is not None:
            return await InventoryService._merge_create_with_existing_lot(
                existing, data.unit_price
            )

        db = await get_db()
        try:
            cursor = await db.execute(
                """
                INSERT INTO lots (material_id, lot_code, unit_price)
                VALUES (?, ?, ?)
                """,
                (data.material_id, data.lot_code, data.unit_price),
            )
            await db.commit()
            lot_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            retry = await InventoryService.get_lot_by_material_and_code(
                data.material_id, data.lot_code
            )
            if retry is not None:
                return await InventoryService._merge_create_with_existing_lot(
                    retry, data.unit_price
                )
            raise
        finally:
            await db.close()

        return await InventoryService.get_lot(lot_id)

    @staticmethod
    async def _merge_lots_into_target(
        source: Lot, target: Lot, final_unit_price: float
    ) -> Lot:
        """
        編集対象ロットの履歴を、同一材料・同一ロットコードの既存ロットへ統合する。
        UNIQUE(material_id, lot_code) によりコード変更だけでは同一コードにできないため、
        取引の lot_id を付け替えてから元ロット行を削除する。
        """
        if source.id == target.id:
            return await InventoryService.get_lot(source.id)
        if source.material_id != target.material_id:
            raise ValueError("材料が異なるロットは統合できません")

        db = await get_db()
        try:
            await db.execute("BEGIN")
            await db.execute(
                "UPDATE transactions SET lot_id = ? WHERE lot_id = ?",
                (target.id, source.id),
            )
            await db.execute(
                "UPDATE lots SET unit_price = ? WHERE id = ?",
                (final_unit_price, target.id),
            )
            await db.execute("DELETE FROM lots WHERE id = ?", (source.id,))
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()

        logger.info(
            "ロット統合: 取引を lot_id=%s から lot_id=%s へ移し、元ロットを削除しました",
            source.id,
            target.id,
        )

        return await InventoryService.get_lot(target.id)

    @staticmethod
    async def update_lot(lot_id: int, data: LotUpdate) -> Optional[Lot]:
        """ロットコード・単価の更新"""
        existing = await InventoryService.get_lot(lot_id)
        if not existing:
            return None

        next_code = data.lot_code if data.lot_code is not None else existing.lot_code
        next_price = data.unit_price if data.unit_price is not None else existing.unit_price

        if (
            next_code == existing.lot_code
            and InventoryService._unit_prices_equal(next_price, existing.unit_price)
        ):
            return existing

        conflict = await InventoryService.get_lot_by_material_and_code(
            existing.material_id, next_code
        )
        if conflict is not None and conflict.id != existing.id:
            return await InventoryService._merge_lots_into_target(
                existing, conflict, next_price
            )

        db = await get_db()
        try:
            cursor = await db.execute(
                "UPDATE lots SET lot_code = ?, unit_price = ? WHERE id = ?",
                (next_code, next_price, lot_id),
            )
            await db.commit()
            if cursor.rowcount == 0:
                return None
        finally:
            await db.close()

        return await InventoryService.get_lot(lot_id)

    @staticmethod
    async def calculate_inventory(material_id: int) -> InventorySummary:
        """
        在庫計算
        在庫重量 = Σ(入庫 + 戻し) - Σ(出庫)
        在庫金額 = Σ(金額)ベース
        """
        db = await get_db()
        try:
            material = await InventoryService.get_material(material_id)
            if not material:
                raise ValueError(f"Material not found: {material_id}")
            lot_summaries_raw = await InventoryService._get_lot_inventory_summaries(db, material_id)
            lot_summaries = [
                InventoryService._normalize_lot_summary_for_display(s, material.weight_per_unit)
                for s in lot_summaries_raw
            ]
            total_quantity = sum(lot.current_quantity for lot in lot_summaries)
            total_effective_quantity = InventoryService._total_effective_quantity(
                lot_summaries,
                material.weight_per_unit,
            )
            total_weight = sum(lot.current_weight for lot in lot_summaries)
            total_value = sum(lot.current_value for lot in lot_summaries)

            return InventorySummary(
                material_id=material_id,
                material_name=material.name,
                weight_per_unit=material.weight_per_unit,
                total_quantity=total_quantity,
                total_effective_quantity=total_effective_quantity,
                total_weight=InventoryService._normalize_zero(total_weight, 3),
                total_value=InventoryService._normalize_zero(total_value, 1),
                lot_summaries=lot_summaries,
                oldest_available_lot_id=InventoryService._get_oldest_available_lot_id(lot_summaries),
            )
        finally:
            await db.close()

    @staticmethod
    async def create_transaction(data: TransactionCreate) -> Transaction:
        """トランザクション作成"""
        db = await get_db()
        try:
            if data.idempotency_key:
                existing = await InventoryService.get_transaction_by_idempotency_key(
                    data.idempotency_key
                )
                if existing:
                    return existing

            if data.type == TransactionType.TRANSFER:
                lot = await InventoryService.get_lot(data.lot_id)
                if not lot or lot.material_id != data.material_id:
                    raise InsufficientInventoryError("移動対象のロットが見つかりません")

                loc_from = await InventoryService.get_stock_location(data.location_from_id)
                loc_to = await InventoryService.get_stock_location(data.location_to_id)
                if not loc_from or not loc_to:
                    raise InsufficientInventoryError("保管場所が見つかりません")

                src_qty, src_weight = await InventoryService._get_lot_location_balance(
                    db, data.lot_id, data.location_from_id
                )
                material = await InventoryService.get_material(data.material_id)
                if not material:
                    raise InsufficientInventoryError("材料が見つかりません")

                effective_src = InventoryService._effective_stock_quantity(
                    src_qty,
                    src_weight,
                    material.weight_per_unit,
                )
                if data.quantity > effective_src or not InventoryService._outbound_weight_within_stock(
                    data.weight, src_weight
                ):
                    raise InsufficientLocationInventoryError(
                        "移動元の場所に十分な在庫がありません"
                    )

                insert_quantity = data.quantity
                insert_weight = data.weight
                insert_quantity = min(insert_quantity, src_qty)
                insert_weight = min(
                    InventoryService._normalize_zero(max(0.0, insert_weight), 3),
                    InventoryService._normalize_zero(src_weight, 3),
                )

                try:
                    cursor = await db.execute(
                        """
                        INSERT INTO transactions
                        (material_id, lot_id, type, quantity, weight, unit_price, memo,
                         idempotency_key, location_id, location_from_id, location_to_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                        """,
                        (
                            data.material_id,
                            data.lot_id,
                            data.type.value,
                            insert_quantity,
                            insert_weight,
                            data.unit_price,
                            data.memo,
                            data.idempotency_key,
                            data.location_from_id,
                            data.location_to_id,
                        ),
                    )
                    await db.commit()
                    tx_id = cursor.lastrowid
                except sqlite3.IntegrityError:
                    if data.idempotency_key:
                        existing = await InventoryService.get_transaction_by_idempotency_key(
                            data.idempotency_key
                        )
                        if existing:
                            return existing
                    raise

                return await InventoryService.get_transaction(tx_id)

            default_location_id = await InventoryService._get_default_location_id()
            resolved_location_id = data.location_id or default_location_id
            location = await InventoryService.get_stock_location(resolved_location_id)
            if not location:
                raise InsufficientInventoryError("保管場所が見つかりません")

            selected_lot = None
            if data.type == TransactionType.OUT:
                inventory = await InventoryService.calculate_inventory(data.material_id)
                if data.quantity > inventory.total_effective_quantity or not InventoryService._outbound_weight_within_stock(
                    data.weight, inventory.total_weight
                ):
                    raise InsufficientInventoryError("在庫不足です")

                selected_lot = next(
                    (lot for lot in inventory.lot_summaries if lot.lot_id == data.lot_id),
                    None,
                )
                if not selected_lot:
                    raise InsufficientInventoryError("出庫対象のロットが見つかりません")

                effective_lot = InventoryService._effective_stock_quantity(
                    selected_lot.current_quantity,
                    selected_lot.current_weight,
                    inventory.weight_per_unit,
                )
                if data.quantity > effective_lot or not InventoryService._outbound_weight_within_stock(
                    data.weight, selected_lot.current_weight
                ):
                    raise InsufficientInventoryError("選択したロットの在庫が不足しています")

                loc_qty, loc_weight = await InventoryService._get_lot_location_balance(
                    db, data.lot_id, resolved_location_id
                )
                effective_loc = InventoryService._effective_stock_quantity(
                    loc_qty,
                    loc_weight,
                    inventory.weight_per_unit,
                )
                if data.quantity > effective_loc or not InventoryService._outbound_weight_within_stock(
                    data.weight, loc_weight
                ):
                    raise InsufficientLocationInventoryError(
                        "選択した保管場所の在庫が不足しています"
                    )

            insert_quantity = data.quantity
            insert_weight = data.weight
            if data.type == TransactionType.OUT:
                insert_quantity = min(data.quantity, selected_lot.current_quantity)
                insert_weight = min(
                    InventoryService._normalize_zero(max(0.0, data.weight), 3),
                    InventoryService._normalize_zero(selected_lot.current_weight, 3),
                )

            try:
                cursor = await db.execute(
                    """
                    INSERT INTO transactions
                    (material_id, lot_id, type, quantity, weight, unit_price, memo,
                     idempotency_key, location_id, location_from_id, location_to_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                    """,
                    (
                        data.material_id,
                        data.lot_id,
                        data.type.value,
                        insert_quantity,
                        insert_weight,
                        data.unit_price,
                        data.memo,
                        data.idempotency_key,
                        resolved_location_id,
                    ),
                )
                await db.commit()
                tx_id = cursor.lastrowid
            except sqlite3.IntegrityError:
                if data.idempotency_key:
                    existing = await InventoryService.get_transaction_by_idempotency_key(
                        data.idempotency_key
                    )
                    if existing:
                        return existing
                raise

            return await InventoryService.get_transaction(tx_id)
        finally:
            await db.close()

    @staticmethod
    async def get_transaction(tx_id: int) -> Optional[Transaction]:
        """トランザクション取得"""
        db = await get_db()
        try:
            cursor = await db.execute(
                """
                SELECT
                    transactions.*,
                    lots.lot_code,
                    sl.name AS location_name,
                    slf.name AS location_from_name,
                    slt.name AS location_to_name
                FROM transactions
                LEFT JOIN lots ON lots.id = transactions.lot_id
                LEFT JOIN stock_locations sl ON sl.id = transactions.location_id
                LEFT JOIN stock_locations slf ON slf.id = transactions.location_from_id
                LEFT JOIN stock_locations slt ON slt.id = transactions.location_to_id
                WHERE transactions.id = ?
                """,
                (tx_id,),
            )
            row = await cursor.fetchone()
            if row:
                return Transaction(**dict(row))
            return None
        finally:
            await db.close()

    @staticmethod
    async def get_transaction_by_idempotency_key(
        idempotency_key: str,
    ) -> Optional[Transaction]:
        """idempotency key でトランザクション取得"""
        db = await get_db()
        try:
            cursor = await db.execute(
                """
                SELECT
                    transactions.*,
                    lots.lot_code,
                    sl.name AS location_name,
                    slf.name AS location_from_name,
                    slt.name AS location_to_name
                FROM transactions
                LEFT JOIN lots ON lots.id = transactions.lot_id
                LEFT JOIN stock_locations sl ON sl.id = transactions.location_id
                LEFT JOIN stock_locations slf ON slf.id = transactions.location_from_id
                LEFT JOIN stock_locations slt ON slt.id = transactions.location_to_id
                WHERE transactions.idempotency_key = ?
                """,
                (idempotency_key,),
            )
            row = await cursor.fetchone()
            if row:
                return Transaction(**dict(row))
            return None
        finally:
            await db.close()

    @staticmethod
    async def get_transactions(
        material_id: Optional[int] = None,
        tx_type: Optional[TransactionType] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Transaction], int]:
        """トランザクション一覧（件数付き）。memo・ロットコード・ID の部分一致検索。"""
        db = await get_db()
        try:
            base_from = """
                FROM transactions
                LEFT JOIN lots ON lots.id = transactions.lot_id
                LEFT JOIN stock_locations sl ON sl.id = transactions.location_id
                LEFT JOIN stock_locations slf ON slf.id = transactions.location_from_id
                LEFT JOIN stock_locations slt ON slt.id = transactions.location_to_id
                WHERE 1=1
            """
            params: list = []

            if material_id:
                base_from += " AND transactions.material_id = ?"
                params.append(material_id)
            if tx_type:
                base_from += " AND transactions.type = ?"
                params.append(tx_type.value)
            if search and search.strip():
                term = f"%{search.strip()}%"
                base_from += (
                    " AND (transactions.memo LIKE ? OR lots.lot_code LIKE ? "
                    "OR CAST(transactions.id AS TEXT) LIKE ?)"
                )
                params.extend([term, term, term])

            count_sql = f"SELECT COUNT(*) AS c {base_from}"
            cursor = await db.execute(count_sql, params)
            count_row = await cursor.fetchone()
            total = int(count_row["c"]) if count_row else 0

            data_sql = (
                f"SELECT transactions.*, lots.lot_code, "
                f"sl.name AS location_name, slf.name AS location_from_name, "
                f"slt.name AS location_to_name {base_from} "
                "ORDER BY transactions.created_at DESC LIMIT ? OFFSET ?"
            )
            cursor = await db.execute(data_sql, params + [limit, offset])
            rows = await cursor.fetchall()
            items = [Transaction(**dict(row)) for row in rows]
            return items, total
        finally:
            await db.close()

    @staticmethod
    async def list_lot_summaries_paginated(
        material_id: int,
        limit: int = 20,
        offset: int = 0,
        search: Optional[str] = None,
        nonzero_only: bool = True,
    ) -> tuple[list[LotInventorySummary], int]:
        """
        ロット別在庫サマリーのページング。
        nonzero_only: True のとき残本数 0 のロットは含めない（ホームのロット一覧向け）。
        """
        material = await InventoryService.get_material(material_id)
        if not material:
            raise ValueError("Material not found")

        db = await get_db()
        try:
            raw = await InventoryService._get_lot_inventory_summaries(db, material_id)
        finally:
            await db.close()

        normalized = [
            InventoryService._normalize_lot_summary_for_display(s, material.weight_per_unit)
            for s in raw
        ]

        if nonzero_only:
            filtered = [s for s in normalized if s.current_quantity > 0]
        else:
            filtered = list(normalized)

        if search and search.strip():
            q = search.strip().lower()
            filtered = [s for s in filtered if q in s.lot_code.lower()]

        total = len(filtered)
        page = filtered[offset : offset + limit]
        return page, total

    @staticmethod
    async def update_transaction(
        tx_id: int, quantity: Optional[int], weight: Optional[float], memo: Optional[str]
    ) -> Optional[Transaction]:
        """トランザクション更新"""
        db = await get_db()
        try:
            updates = []
            params = []

            if quantity is not None:
                updates.append("quantity = ?")
                params.append(quantity)
            if weight is not None:
                updates.append("weight = ?")
                params.append(weight)
            if memo is not None:
                updates.append("memo = ?")
                params.append(memo)

            if not updates:
                return await InventoryService.get_transaction(tx_id)

            params.append(tx_id)
            await db.execute(
                f"UPDATE transactions SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await db.commit()

            return await InventoryService.get_transaction(tx_id)
        finally:
            await db.close()

    @staticmethod
    async def delete_transaction(tx_id: int) -> bool:
        """トランザクション削除"""
        db = await get_db()
        try:
            cursor = await db.execute(
                "DELETE FROM transactions WHERE id = ?", (tx_id,)
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    @staticmethod
    async def get_dashboard() -> DashboardStats:
        """ダッシュボードデータ取得"""
        materials = await InventoryService.get_all_materials()
        if not materials:
            raise ValueError("No materials found")

        material = materials[0]
        inventory = await InventoryService.calculate_inventory(material.id)
        recent, _ = await InventoryService.get_transactions(
            material_id=material.id,
            limit=5,
            offset=0,
        )

        return DashboardStats(
            material=material,
            total_quantity=inventory.total_quantity,
            total_effective_quantity=inventory.total_effective_quantity,
            total_weight=inventory.total_weight,
            total_value=inventory.total_value,
            lot_summaries=inventory.lot_summaries,
            oldest_available_lot_id=inventory.oldest_available_lot_id,
            recent_transactions=recent,
        )
