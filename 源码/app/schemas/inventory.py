"""库存出入库 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InventoryChangeRequest(BaseModel):
    """入库/出库请求体。"""

    product_id: int = Field(gt=0, description="商品ID")
    quantity: int = Field(
        gt=0,
        description="入库或出库数量，必须大于 0",
    )
    operator: str | None = Field(
        default=None,
        max_length=64,
        description="操作人",
    )
    remark: str | None = Field(
        default=None,
        max_length=255,
        description="备注",
    )


class InventoryLogOut(BaseModel):
    """出入库流水响应结构。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    change_type: str
    change_quantity: int
    before_quantity: int
    after_quantity: int
    operated_at: datetime
    operator: str | None
    remark: str | None
