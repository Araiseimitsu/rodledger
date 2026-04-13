"""本数・重量の実効在庫判定（丸め誤差）の単体テスト"""
from datetime import datetime, timezone

import pytest

from app.models.models import LotInventorySummary
from app.services.inventory_service import InventoryService


@pytest.mark.parametrize(
    ("quantity", "weight", "weight_per_unit", "expected"),
    [
        (0, 0.001, 0.5, 0),
        (0, 0.0, 0.5, 0),
        (0, 0.6, 0.5, 1),
        (3, 0.001, 0.5, 3),
        (0, 0.25, 0.5, 1),
    ],
)
def test_effective_stock_quantity(quantity, weight, weight_per_unit, expected):
    assert (
        InventoryService._effective_stock_quantity(quantity, weight, weight_per_unit)
        == expected
    )


def test_quantity_from_weight_matches_frontend_style_dust():
    assert InventoryService._quantity_from_weight_like_frontend(0.001, 0.5) == 0


def test_outbound_weight_within_stock_allows_rounding_gap():
    """本数×単重の換算が取引の積み上げ残重量より 0.001kg だけ大きい場合は出庫可"""
    assert InventoryService._outbound_weight_within_stock(90.5, 90.499)


def test_outbound_weight_within_stock_rejects_clear_shortage():
    assert not InventoryService._outbound_weight_within_stock(90.502, 90.499)


@pytest.mark.parametrize(
    ("quantity", "weight", "weight_per_unit", "expected_q", "expected_w"),
    [
        (0, 0.008, 0.5, 0, 0.0),
        (0, 0.008, 2.5, 0, 0.0),
        (3, 0.0, 0.5, 0, 0.0),
        (0, 0.6, 0.5, 0, 0.6),
        (2, 1.0, 0.5, 2, 1.0),
    ],
)
def test_coupled_display_quantity_weight(
    quantity, weight, weight_per_unit, expected_q, expected_w
):
    q, w = InventoryService._coupled_display_quantity_weight(
        quantity, weight, weight_per_unit
    )
    assert q == expected_q
    assert w == expected_w


def test_total_effective_quantity_sums_lots():
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    lots = [
        LotInventorySummary(
            lot_id=1,
            lot_code="A",
            unit_price=100.0,
            created_at=base,
            current_quantity=0,
            current_weight=0.6,
            current_value=0.0,
        ),
        LotInventorySummary(
            lot_id=2,
            lot_code="B",
            unit_price=100.0,
            created_at=base,
            current_quantity=2,
            current_weight=0.0,
            current_value=0.0,
        ),
    ]
    assert InventoryService._total_effective_quantity(lots, 0.5) == 3
