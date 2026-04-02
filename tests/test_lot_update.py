"""LotUpdate スキーマの検証"""
import pytest
from pydantic import ValidationError

from app.models.models import LotUpdate


def test_lot_update_accepts_unit_price_only():
    m = LotUpdate(unit_price=275.0)
    assert m.unit_price == 275.0
    assert m.lot_code is None


def test_lot_update_accepts_lot_code_only():
    m = LotUpdate(lot_code="LOT-NEW")
    assert m.lot_code == "LOT-NEW"
    assert m.unit_price is None


def test_lot_update_strips_lot_code():
    m = LotUpdate(lot_code="  ABC-001  ")
    assert m.lot_code == "ABC-001"


def test_lot_update_rejects_empty_body():
    with pytest.raises(ValidationError):
        LotUpdate()


def test_lot_update_rejects_empty_lot_code_string():
    with pytest.raises(ValidationError):
        LotUpdate(lot_code="   ")


def test_lot_update_rejects_non_positive_unit_price():
    with pytest.raises(ValidationError):
        LotUpdate(unit_price=0)

