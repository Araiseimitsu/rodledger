"""
Pydantic スキーマ定義
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class TransactionType(str, Enum):
    """トランザクション種別"""
    IN = "in"
    OUT = "out"
    RETURN = "return"
    ADJUST = "adjust"


# ============ Material ============
class MaterialBase(BaseModel):
    name: str
    diameter: float
    length: float
    density: float
    weight_per_unit: float


class MaterialCreate(MaterialBase):
    pass


class MaterialUpdate(BaseModel):
    diameter: Optional[float] = Field(default=None, gt=0)
    length: Optional[float] = Field(default=None, gt=0)
    density: Optional[float] = Field(default=None, gt=0)


class Material(MaterialBase):
    id: int

    class Config:
        from_attributes = True


# ============ Lot ============
class LotBase(BaseModel):
    material_id: int
    lot_code: str
    unit_price: float = Field(description="円/kg")


class LotCreate(LotBase):
    pass


class LotUpdate(BaseModel):
    unit_price: float = Field(gt=0, description="円/kg")


class Lot(LotBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Transaction ============
class TransactionBase(BaseModel):
    material_id: int
    lot_id: int
    type: TransactionType
    quantity: int = Field(ge=0, description="本数")
    weight: float = Field(ge=0, description="kg")
    memo: Optional[str] = None
    idempotency_key: Optional[str] = None

    @model_validator(mode="after")
    def validate_amounts(self):
        if self.quantity == 0 and self.weight == 0:
            raise ValueError("数量または重量のどちらかを入力してください")
        return self


class TransactionCreate(TransactionBase):
    unit_price: float = Field(description="履歴保持用")


class TransactionUpdate(BaseModel):
    quantity: Optional[int] = Field(default=None, ge=0)
    weight: Optional[float] = Field(default=None, ge=0)
    memo: Optional[str] = None


class Transaction(TransactionBase):
    id: int
    unit_price: float
    created_at: datetime
    lot_code: Optional[str] = None

    class Config:
        from_attributes = True


# ============ Inventory ============
class LotInventorySummary(BaseModel):
    """ロット別在庫サマリー"""
    lot_id: int
    lot_code: str
    unit_price: float
    created_at: datetime
    current_quantity: int
    current_weight: float
    current_value: float


class InventorySummary(BaseModel):
    """在庫サマリー"""
    material_id: int
    material_name: str
    total_quantity: int
    total_weight: float
    total_value: float
    lot_summaries: list[LotInventorySummary] = Field(default_factory=list)
    oldest_available_lot_id: Optional[int] = None


class DashboardStats(BaseModel):
    """ダッシュボード統計"""
    material: Material
    total_quantity: int
    total_weight: float
    total_value: float
    lot_summaries: list[LotInventorySummary] = Field(default_factory=list)
    oldest_available_lot_id: Optional[int] = None
    recent_transactions: list[Transaction]
