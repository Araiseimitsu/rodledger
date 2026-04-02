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
    PaginatedTransactions,
    PaginatedLots,
    PaginatedLotSummaries,
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
    """ロットコード・単価の更新"""
    try:
        lot = await InventoryService.update_lot(lot_id, data)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Lot code already exists") from exc
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


@router.get("/inventory/{material_id}/lot-summaries", response_model=PaginatedLotSummaries)
async def list_lot_summaries_paginated(
    material_id: int,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, description="ロットコードの部分一致"),
    nonzero_only: bool = Query(True, description="残本数0のロットを除く"),
):
    """ロット別在庫サマリーのページング（ホームのロット一覧用）"""
    try:
        items, total = await InventoryService.list_lot_summaries_paginated(
            material_id, limit, offset, q, nonzero_only
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PaginatedLotSummaries(items=items, total=total)


@router.get("/inventory/{material_id}", response_model=InventorySummary)
async def get_inventory(material_id: int):
    """在庫サマリー取得"""
    inventory = await InventoryService.calculate_inventory(material_id)
    if not inventory:
        raise HTTPException(status_code=404, detail="Material not found")
    return inventory


@router.get("/transactions", response_model=PaginatedTransactions)
async def list_transactions(
    material_id: Optional[int] = Query(None),
    type: Optional[TransactionType] = Query(None),
    q: Optional[str] = Query(None, description="メモ・ロットコード・取引IDの部分一致"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """トランザクション一覧（ページング・検索）"""
    items, total = await InventoryService.get_transactions(
        material_id=material_id,
        tx_type=type,
        search=q,
        limit=limit,
        offset=offset,
    )
    return PaginatedTransactions(items=items, total=total)


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


@router.get("/lots/{material_id}", response_model=PaginatedLots)
async def get_lots(
    material_id: int,
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=5000,
        description="未指定時は全件",
    ),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, description="ロットコードの部分一致"),
):
    """材料に紐づくロット一覧（ページング・検索）"""
    items, total = await InventoryService.get_lots_by_material(
        material_id, limit=limit, offset=offset, search=q
    )
    return PaginatedLots(items=items, total=total)
