"""商品 ORM 模型。"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import BIGINT_ID

if TYPE_CHECKING:
    # 仅用于类型检查，避免运行时循环导入。
    from app.models.category import Category
    from app.models.inventory_log import InventoryLog


class Product(Base):
    """对应数据库表 products。"""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(
        BIGINT_ID,
        primary_key=True,
        autoincrement=True,
        comment="商品ID",
    )
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("categories.id"),
        nullable=False,
        index=True,
        comment="商品分类ID",
    )
    product_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="商品名称",
    )
    sku: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="商品SKU，全局唯一",
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="当前库存数量",
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="销售价格",
    )
    cost: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="成本价，用于统计库存总价值",
    )

    unit: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="件",
        comment="计量单位",
    )
    low_stock_threshold: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        comment="低库存阈值",
    )

    last_inbound_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="最近一次入库时间",
    )
    last_outbound_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="最近一次出库时间",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )

    # 商品所属分类。
    category: Mapped["Category"] = relationship(
        back_populates="products",
    )
    # 商品的所有出入库流水。
    inventory_logs: Mapped[list["InventoryLog"]] = relationship(
        back_populates="product",
    )

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<Product id={self.id} sku={self.sku!r} "
            f"quantity={self.quantity}>"
        )
