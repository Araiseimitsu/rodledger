"""ロット在庫リセット機能のテスト"""
import pytest
from pydantic import ValidationError

from app.models.models import TransactionType, TransactionCreate


def test_reset_transaction_type_exists():
    """RESETトランザクションタイプが存在することを確認"""
    assert hasattr(TransactionType, 'RESET')
    assert TransactionType.RESET.value == "reset"


def test_reset_transaction_create_validation():
    """RESETトランザクションのバリデーションが通ることを確認"""
    data = TransactionCreate(
        material_id=1,
        lot_id=1,
        type=TransactionType.RESET,
        quantity=0,
        weight=0,
        unit_price=150.0,
    )
    assert data.type == TransactionType.RESET
    assert data.quantity == 0
    assert data.weight == 0


def test_reset_transaction_create_with_memo():
    """RESETトランザクションがメモ付きで作成できることを確認"""
    data = TransactionCreate(
        material_id=1,
        lot_id=1,
        type=TransactionType.RESET,
        quantity=0,
        weight=0,
        unit_price=150.0,
        memo="在庫リセット",
    )
    assert data.memo == "在庫リセット"


def test_reset_transaction_create_without_location():
    """RESETトランザクションがlocation_idなしで作成できることを確認"""
    data = TransactionCreate(
        material_id=1,
        lot_id=1,
        type=TransactionType.RESET,
        quantity=0,
        weight=0,
        unit_price=150.0,
    )
    assert data.location_id is None
    assert data.location_from_id is None
    assert data.location_to_id is None


def test_other_transaction_types_require_quantity_or_weight():
    """RESET以外のトランザクションは数量または重量が必要なことを確認"""
    with pytest.raises(ValidationError):
        TransactionCreate(
            material_id=1,
            lot_id=1,
            type=TransactionType.IN,
            quantity=0,
            weight=0,
            unit_price=150.0,
        )


def test_reset_transaction_allows_zero_quantity_and_weight():
    """RESETトランザクションがquantity=0, weight=0を許可することを確認"""
    data = TransactionCreate(
        material_id=1,
        lot_id=1,
        type=TransactionType.RESET,
        quantity=0,
        weight=0,
        unit_price=150.0,
    )
    assert data.quantity == 0
    assert data.weight == 0
