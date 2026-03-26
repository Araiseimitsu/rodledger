"""
トランザクション API ルーター
"""
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.models import (
    Material,
    MaterialUpdate,
    Lot,
    LotCreate,
    LotUpdate,
    Transaction,
    TransactionCreate,
    TransactionType,
    InventorySummary,
    DashboardStats,
)
from app.services.inventory_service import InventoryService, InsufficientInventoryError

router = APIRouter(prefix="/api", tags=["transactions"])


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard():
    """ダッシュボード統計取得"""
    return await InventoryService.get_dashboard()


@router.put("/materials/{material_id}", response_model=Material)
async def update_material(material_id: int, data: MaterialUpdate):
    """材料マスタ更新"""
    material = await InventoryService.update_material(material_id, data)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    return material


@router.put("/lots/{lot_id}", response_model=Lot)
async def update_lot(lot_id: int, data: LotUpdate):
    """ロット単価更新"""
    lot = await InventoryService.update_lot(lot_id, data)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    return lot


@router.post("/lots", response_model=Lot, status_code=201)
async def create_lot(data: LotCreate):
    """ロット作成"""
    material = await InventoryService.get_material(data.material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    try:
        return await InventoryService.create_lot(data)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Lot code already exists") from exc


@router.get("/inventory/{material_id}", response_model=InventorySummary)
async def get_inventory(material_id: int):
    """在庫サマリー取得"""
    inventory = await InventoryService.calculate_inventory(material_id)
    if not inventory:
        raise HTTPException(status_code=404, detail="Material not found")
    return inventory


@router.get("/transactions", response_model=list[Transaction])
async def list_transactions(
    material_id: Optional[int] = Query(None),
    type: Optional[TransactionType] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """トランザクション一覧"""
    return await InventoryService.get_transactions(material_id, type, limit, offset)


@router.post("/transactions", response_model=Transaction, status_code=201)
async def create_transaction(data: TransactionCreate):
    """トランザクション作成（入庫/出庫/戻し/修正）"""
    material = await InventoryService.get_material(data.material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    lot = await InventoryService.get_lot(data.lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")

    if lot.material_id != data.material_id:
        raise HTTPException(status_code=400, detail="Lot does not match material")

    # ロットの単価を取得（未指定の場合）
    if not data.unit_price:
        data.unit_price = lot.unit_price

    try:
        return await InventoryService.create_transaction(data)
    except InsufficientInventoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/transactions/{tx_id}", response_model=Transaction)
async def get_transaction(tx_id: int):
    """トランザクション詳細"""
    tx = await InventoryService.get_transaction(tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx


@router.put("/transactions/{tx_id}", response_model=Transaction)
async def update_transaction(
    tx_id: int,
    quantity: Optional[int] = Query(None),
    weight: Optional[float] = Query(None),
    memo: Optional[str] = Query(None),
):
    """トランザクション更新"""
    tx = await InventoryService.update_transaction(tx_id, quantity, weight, memo)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx


@router.delete("/transactions/{tx_id}", status_code=204)
async def delete_transaction(tx_id: int):
    """トランザクション削除"""
    deleted = await InventoryService.delete_transaction(tx_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found")


@router.get("/lots/{material_id}", response_model=list)
async def get_lots(material_id: int):
    """材料に紐づくロット一覧"""
    return await InventoryService.get_lots_by_material(material_id)
