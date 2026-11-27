"""仓库与库存调拨 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ----------------------------------------------------------------------
# 仓库
# ----------------------------------------------------------------------
class WarehouseCreate(BaseModel):
    """创建仓库。"""

    code: str = Field(
        min_length=2,
        max_length=32,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="仓库编码，例如 WH-SH",
    )
    name: str = Field(min_length=1, max_length=64, description="仓库名称")
    address: str | None = Field(default=None, max_length=255)


class WarehouseOut(BaseModel):
    """仓库响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    address: str | None
    is_default: bool
    created_at: datetime


# ----------------------------------------------------------------------
# 调拨
# ----------------------------------------------------------------------
class TransferItemCreate(BaseModel):
    """调拨明细。"""

    product_id: int = Field(gt=0, description="商品ID")
    quantity: int = Field(gt=0, description="调拨数量")


class TransferCreate(BaseModel):
    """创建调拨单。"""

    from_warehouse_id: int = Field(gt=0, description="调出仓库ID")
    to_warehouse_id: int = Field(gt=0, description="调入仓库ID")
    items: list[TransferItemCreate] = Field(
        min_length=1,
        description="调拨商品列表",
    )
    operator: str | None = Field(default=None, max_length=64)
    remark: str | None = Field(default=None, max_length=255)


class TransferItemOut(BaseModel):
    """调拨明细响应。"""

    model_config = ConfigDict(from_attributes=True)

    product_id: int
    sku: str
    product_name: str
    quantity: int


class WarehouseBrief(BaseModel):
    """调拨单中嵌套的仓库简要信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class TransferOut(BaseModel):
    """调拨单响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    transfer_no: str
    status: str
    operator: str | None
    remark: str | None
    created_at: datetime
    from_warehouse: WarehouseBrief
    to_warehouse: WarehouseBrief
    items: list[TransferItemOut]
