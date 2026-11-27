"""商品分类 ORM 模型。"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    # 仅用于类型检查，避免运行时循环导入。
    from app.models.product import Product


class Category(Base):
    """对应数据库表 categories。"""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="分类ID",
    )
    category_name: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        comment="分类名称，例如：服装、鞋子",
    )
    sku_prefix: Mapped[str] = mapped_column(
        String(8),
        unique=True,
        nullable=False,
        comment="SKU 前缀，例如：FZ、XZ",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )

    # 一个分类下可以有多个商品。
    products: Mapped[list["Product"]] = relationship(
        back_populates="category",
    )

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return f"<Category id={self.id} name={self.category_name!r}>"
