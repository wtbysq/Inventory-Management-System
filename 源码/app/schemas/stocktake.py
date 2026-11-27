"""库存盘点 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StocktakeCreate(BaseModel):
    """创建盘点单。

    两个筛选条件至少提供一个：
        - category_id: 只盘点某个分类
        - product_ids: 只盘点指定商品
    都不传时盘点全部商品。
    """

    category_id: int | None = Field(
        default=None,
        ge=1,
        description="分类ID，不传表示全部分类",
    )
    product_ids: list[int] | None = Field(
        default=None,
        description="指定商品ID列表，与 category_id 二选一",
    )
    operator: str | None = Field(default=None, max_length=64)
    remark: str | None = Field(default=None, max_length=255)


class StocktakeCountItem(BaseModel):
    """单条实盘录入。"""

    product_id: int = Field(gt=0, description="商品ID")
    counted_quantity: int = Field(ge=0, description="实盘数量，不能为负")
    remark: str | None = Field(default=None, max_length=255)


class StocktakeCountRequest(BaseModel):
    """批量录入实盘数量。"""

    items: list[StocktakeCountItem] = Field(
        min_length=1,
        description="至少录入一条",
    )


class StocktakeItemOut(BaseModel):
    """盘点明细响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    sku: str
    product_name: str
    expected_quantity: int
    counted_quantity: int | None
    difference: int | None
    remark: str | None


class StocktakeOut(BaseModel):
    """盘点单响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    stocktake_no: str
    status: str
    scope: str | None
    operator: str | None
    remark: str | None
    created_at: datetime
    confirmed_at: datetime | None
    items: list[StocktakeItemOut]
