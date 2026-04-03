"""ロット更新で同一材料・同一コードの既存ロットへ統合する処理の結合テスト"""
import asyncio
from pathlib import Path

import pytest

from app import database
from app.models.models import (
    LotCreate,
    LotUpdate,
    TransactionCreate,
    TransactionType,
)
from app.services.inventory_service import InventoryService


@pytest.fixture
def temp_db(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "rodledger_test.db"
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    yield db_path


async def _run_merge_scenario():
    await database.init_db()

    wrong = await InventoryService.create_lot(
        LotCreate(material_id=1, lot_code="WRONG-LOT", unit_price=275.0)
    )

    await InventoryService.create_transaction(
        TransactionCreate(
            material_id=1,
            lot_id=wrong.id,
            type=TransactionType.IN,
            quantity=5,
            weight=5.0,
            unit_price=275.0,
            memo="誤入庫",
        )
    )

    merged = await InventoryService.update_lot(
        wrong.id,
        LotUpdate(lot_code="LOT-SUM22-001", unit_price=275.0),
    )
    assert merged is not None
    assert merged.lot_code == "LOT-SUM22-001"
    assert merged.id == 1

    assert await InventoryService.get_lot(wrong.id) is None

    inv = await InventoryService.calculate_inventory(1)
    lot1 = next(s for s in inv.lot_summaries if s.lot_id == 1)
    assert lot1.current_quantity == 105


def test_merge_lot_into_existing_on_code_collision(temp_db):
    asyncio.run(_run_merge_scenario())


async def _run_location_note_scenario():
    await database.init_db()

    tx = await InventoryService.create_transaction(
        TransactionCreate(
            material_id=1,
            lot_id=1,
            type=TransactionType.IN,
            quantity=5,
            weight=4.965,
            unit_price=275.0,
            memo="置き場複数",
            location_note="棚番 1, 棚番 2, 棚番 5",
            location_id=1,
        )
    )

    assert tx.location_note == "棚番 1, 棚番 2, 棚番 5"

    fetched = await InventoryService.get_transaction(tx.id)
    assert fetched is not None
    assert fetched.location_note == "棚番 1, 棚番 2, 棚番 5"


def test_inbound_location_note_is_persisted(temp_db):
    asyncio.run(_run_location_note_scenario())
