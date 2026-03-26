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
    LotUpdate,
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

            cursor = await db.execute(
                """
                SELECT
                    SUM(CASE WHEN type IN ('in', 'return') THEN quantity ELSE -quantity END) as total_qty,
                    SUM(CASE WHEN type IN ('in', 'return') THEN weight ELSE -weight END) as total_weight,
                    SUM(CASE
                        WHEN type = 'in' THEN weight * unit_price
                        WHEN type = 'return' THEN weight * unit_price
                        WHEN type = 'out' THEN -weight * unit_price
                        ELSE 0
                    END) as total_value
                FROM transactions
                WHERE material_id = ?
                """,
                (material_id,),
            )
            row = await cursor.fetchone()

            return InventorySummary(
                material_id=material_id,
                material_name=material.name,
                total_quantity=row["total_qty"] or 0,
                total_weight=round(row["total_weight"] or 0.0, 3),
                total_value=round(row["total_value"] or 0.0, 1),
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
                if data.quantity > inventory.total_quantity or data.weight > inventory.total_weight:
                    raise InsufficientInventoryError("在庫不足です")

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
                        data.quantity,
                        data.weight,
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
                "SELECT * FROM transactions WHERE id = ?", (tx_id,)
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
                "SELECT * FROM transactions WHERE idempotency_key = ?",
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
            query = "SELECT * FROM transactions WHERE 1=1"
            params = []

            if material_id:
                query += " AND material_id = ?"
                params.append(material_id)
            if tx_type:
                query += " AND type = ?"
                params.append(tx_type.value)

            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
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
            total_weight=inventory.total_weight,
            total_value=inventory.total_value,
            recent_transactions=recent,
        )
