"""商品 Schema。"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductOut(BaseModel):
    """商品响应结构。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    product_name: str
    sku: str

    quantity: int = Field(description="当前库存数量")
    price: Decimal = Field(description="销售价格")
    cost: Decimal | None = Field(default=None, description="成本价")

    unit: str
    low_stock_threshold: int

    last_inbound_at: datetime | None
    last_outbound_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProductStats(BaseModel):
    """库存统计结果。"""

    total_products: int = Field(description="商品种类数")
    total_quantity: int = Field(description="所有商品库存总数量")
    total_inventory_value: Decimal = Field(
        description="库存总价值，按 quantity * cost 计算"
    )
    low_stock_count: int = Field(description="低库存商品数量")
