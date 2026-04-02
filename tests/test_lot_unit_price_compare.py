"""ロット単価の浮動小数比較（更新のノーオプ判定）"""
from app.services.inventory_service import InventoryService


def test_unit_prices_equal_same_value():
    assert InventoryService._unit_prices_equal(275.0, 275.0)


def test_unit_prices_equal_rejects_different():
    assert not InventoryService._unit_prices_equal(275.0, 276.0)
