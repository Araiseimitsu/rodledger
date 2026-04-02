"""
Pydantic スキーマ定義
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class TransactionType(str, Enum):
    """トランザクション種別"""
    IN = "in"
    OUT = "out"
    RETURN = "return"
    ADJUST = "adjust"
    TRANSFER = "transfer"


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
    """ロットのロットコード・単価の更新（いずれか一方以上を指定）"""

    lot_code: Optional[str] = None
    unit_price: Optional[float] = Field(default=None, gt=0, description="円/kg")

    @field_validator("lot_code", mode="before")
    @classmethod
    def normalize_lot_code(cls, v):
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("lot_code は文字列で指定してください")
        stripped = v.strip()
        if not stripped:
            raise ValueError("ロットコードを空にすることはできません")
        return stripped

    @model_validator(mode="after")
    def require_at_least_one(self):
        if self.lot_code is None and self.unit_price is None:
            raise ValueError("lot_code または unit_price のいずれかを指定してください")
        return self


class Lot(LotBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Stock location ============
SHELF_NUMBER_MIN = 1
SHELF_NUMBER_MAX = 299


def normalize_shelf_number(value: object) -> str:
    """
    置き場は棚番 1〜299 の整数のみ（DB の name に正規化した文字列で保持）。
    """
    if isinstance(value, int):
        s = str(value)
    elif isinstance(value, str):
        s = value.strip()
    else:
        raise ValueError("棚番は1〜299の整数で指定してください")
    if not s.isdigit():
        raise ValueError("棚番は1〜299の整数で指定してください")
    n = int(s)
    if n < SHELF_NUMBER_MIN or n > SHELF_NUMBER_MAX:
        raise ValueError(f"棚番は{SHELF_NUMBER_MIN}〜{SHELF_NUMBER_MAX}の範囲で指定してください")
    return str(n)


class StockLocationBase(BaseModel):
    name: str = Field(min_length=1, description=f"棚番（{SHELF_NUMBER_MIN}〜{SHELF_NUMBER_MAX}）")
    sort_order: int = Field(default=0, description="表示順（棚番と同じ値を推奨）")

    @field_validator("name", mode="before")
    @classmethod
    def validate_shelf_name(cls, v):
        return normalize_shelf_number(v)


class StockLocationCreate(StockLocationBase):
    pass


class StockLocationUpdate(BaseModel):
    """棚番・表示順の更新（いずれか一方以上）"""

    name: Optional[str] = None
    sort_order: Optional[int] = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v):
        if v is None:
            return None
        return normalize_shelf_number(v)

    @model_validator(mode="after")
    def require_at_least_one(self):
        if self.name is None and self.sort_order is None:
            raise ValueError("name または sort_order のいずれかを指定してください")
        return self


class StockLocation(StockLocationBase):
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
    location_id: Optional[int] = Field(
        default=None,
        description="入庫・出庫・戻し・修正の対象場所（未指定時は既定の場所）",
    )
    location_from_id: Optional[int] = Field(
        default=None,
        description="移動元（type=transfer のとき必須）",
    )
    location_to_id: Optional[int] = Field(
        default=None,
        description="移動先（type=transfer のとき必須）",
    )

    @model_validator(mode="after")
    def validate_location_fields(self):
        if self.type == TransactionType.TRANSFER:
            if self.location_from_id is None or self.location_to_id is None:
                raise ValueError("移動では移動元・移動先の場所 ID を指定してください")
            if self.location_from_id == self.location_to_id:
                raise ValueError("移動元と移動先は異なる場所を指定してください")
            return self
        if self.location_from_id is not None or self.location_to_id is not None:
            raise ValueError("移動以外では location_from_id / location_to_id は指定できません")
        return self


class TransactionUpdate(BaseModel):
    quantity: Optional[int] = Field(default=None, ge=0)
    weight: Optional[float] = Field(default=None, ge=0)
    memo: Optional[str] = None


class Transaction(TransactionBase):
    id: int
    unit_price: float
    created_at: datetime
    lot_code: Optional[str] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    location_from_id: Optional[int] = None
    location_to_id: Optional[int] = None
    location_from_name: Optional[str] = None
    location_to_name: Optional[str] = None

    class Config:
        from_attributes = True


class LotLocationStock(BaseModel):
    """ロット×保管場所の残数量・重量"""

    location_id: int
    location_name: str
    current_quantity: int
    current_weight: float


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
    weight_per_unit: float
    total_quantity: int
    total_effective_quantity: int
    total_weight: float
    total_value: float
    lot_summaries: list[LotInventorySummary] = Field(default_factory=list)
    oldest_available_lot_id: Optional[int] = None


class DashboardStats(BaseModel):
    """ダッシュボード統計"""
    material: Material
    total_quantity: int
    total_effective_quantity: int
    total_weight: float
    total_value: float
    lot_summaries: list[LotInventorySummary] = Field(default_factory=list)
    oldest_available_lot_id: Optional[int] = None
    recent_transactions: list[Transaction]


class PaginatedTransactions(BaseModel):
    """ページング付きトランザクション一覧"""
    items: list[Transaction]
    total: int


class PaginatedLots(BaseModel):
    """ページング付きロット一覧"""
    items: list[Lot]
    total: int


class PaginatedLotSummaries(BaseModel):
    """ページング付きロット別在庫サマリー"""
    items: list[LotInventorySummary]
    total: int


class LotLocationStocksResponse(BaseModel):
    """ロットの場所別在庫一覧"""

    lot_id: int
    items: list[LotLocationStock]
