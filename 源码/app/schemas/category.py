"""商品分类 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CategoryOut(BaseModel):
    """分类响应结构。"""

    # from_attributes=True 允许直接从 SQLAlchemy ORM 对象转换。
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_name: str
    sku_prefix: str
    created_at: datetime
