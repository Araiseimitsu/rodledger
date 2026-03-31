"""
在庫計算サービス
"""
import math
from typing import Optional
import sqlite3

from app.database import get_db
from app.models.models import (
    Material,
    MaterialUpdate,
    Lot,
    LotCreate,
    LotUpdate,
    LotInventorySummary,
    Transaction,
    TransactionCreate,
    TransactionType,
    InventorySummary,
    DashboardStats,
)


class InsufficientInventoryError(Exception):
    """在庫不足を表す例外"""


class InventoryService:
    """在庫計算ロジック"""

    # 重量は 0.001kg 単位で表示・積み上げるため、本数×単重の換算値が残重量をわずかに超えることがある
    _OUTBOUND_WEIGHT_TOLERANCE_KG = 0.001

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
        """実効在庫ゼロのロットは表示・FIFO・合計から除外する（本数・重量・金額を 0 に正規化）"""
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
        """材料に紐づくロット別在庫を FIFO 順で集計する"""
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
        """FIFO で次に使用すべきロット ID を返す"""
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
    async def get_lots_by_material(material_id: int) -> list[Lot]:
        """材料に紐づくロット一覧"""
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM lots WHERE material_id = ? ORDER BY created_at DESC",
                (material_id,),
            )
            rows = await cursor.fetchall()
            return [Lot(**dict(row)) for row in rows]
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
    async def create_lot(data: LotCreate) -> Lot:
        """ロット作成"""
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
        finally:
            await db.close()

        return await InventoryService.get_lot(lot_id)

    @staticmethod
    async def update_lot(lot_id: int, data: LotUpdate) -> Optional[Lot]:
        """ロット単価更新"""
        db = await get_db()
        try:
            cursor = await db.execute(
                "UPDATE lots SET unit_price = ? WHERE id = ?",
                (data.unit_price, lot_id),
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

                oldest_available_lot_id = inventory.oldest_available_lot_id
                if oldest_available_lot_id and oldest_available_lot_id != data.lot_id:
                    raise InsufficientInventoryError("古いロットから順に出庫してください")

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
                    (material_id, lot_id, type, quantity, weight, unit_price, memo, idempotency_key)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                SELECT transactions.*, lots.lot_code
                FROM transactions
                LEFT JOIN lots ON lots.id = transactions.lot_id
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
                SELECT transactions.*, lots.lot_code
                FROM transactions
                LEFT JOIN lots ON lots.id = transactions.lot_id
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
        limit: int = 50,
        offset: int = 0,
    ) -> list[Transaction]:
        """トランザクション一覧"""
        db = await get_db()
        try:
            query = """
                SELECT transactions.*, lots.lot_code
                FROM transactions
                LEFT JOIN lots ON lots.id = transactions.lot_id
                WHERE 1=1
            """
            params = []

            if material_id:
                query += " AND transactions.material_id = ?"
                params.append(material_id)
            if tx_type:
                query += " AND transactions.type = ?"
                params.append(tx_type.value)

            query += " ORDER BY transactions.created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [Transaction(**dict(row)) for row in rows]
        finally:
            await db.close()

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
        recent = await InventoryService.get_transactions(material.id, limit=5)

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
