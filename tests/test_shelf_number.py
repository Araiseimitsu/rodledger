"""棚番 1〜299 の正規化"""
import pytest
from pydantic import ValidationError

from app.models.models import StockLocationCreate, normalize_shelf_number


def test_normalize_shelf_number_accepts_bounds():
    assert normalize_shelf_number("1") == "1"
    assert normalize_shelf_number("299") == "299"
    assert normalize_shelf_number(42) == "42"


@pytest.mark.parametrize(
    "bad",
    ["0", "300", "abc", "  ", "1.5", "-1"],
)
def test_normalize_shelf_number_rejects(bad):
    with pytest.raises(ValueError):
        normalize_shelf_number(bad)


def test_stock_location_create_accepts_valid():
    m = StockLocationCreate(name="12", sort_order=12)
    assert m.name == "12"


def test_stock_location_create_rejects_out_of_range():
    with pytest.raises(ValidationError):
        StockLocationCreate(name="300", sort_order=0)


def test_create_stock_location_service_rejects():
    import asyncio

    from app.models.models import StockLocationCreate
    from app.services.inventory_service import InventoryService

    async def run():
        with pytest.raises(ValueError, match="すべて登録済み"):
            await InventoryService.create_stock_location(
                StockLocationCreate(name="10", sort_order=10)
            )

    asyncio.run(run())
