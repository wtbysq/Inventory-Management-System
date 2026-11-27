"""库存盘点 ORM 模型。

盘点流程:
    1. 创建盘点单：把当前商品库存抄成“账面数量”（expected_quantity）；
    2. 录入实盘数量（counted_quantity）；
    3. 确认盘点：把 difference = 实盘 - 账面 写入库存，
       同时生成 ADJUST 类型的库存流水。

为什么必须快照账面数量？
    创建盘点单和确认盘点之间，可能还有人下单/入库。
    如果确认时直接拿最新库存当账面，差异就失真了。
    因此 expected_quantity 是创建时的快照，差异计算也基于快照。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import BIGINT_UNSIGNED_ID

if TYPE_CHECKING:
    # 仅用于类型检查，避免运行时循环导入。
    from app.models.product import Product

# 盘点单状态。
STOCKTAKE_STATUS_COUNTING = "COUNTING"
STOCKTAKE_STATUS_CONFIRMED = "CONFIRMED"
STOCKTAKE_STATUS_CANCELLED = "CANCELLED"

STOCKTAKE_STATUSES: tuple[str, ...] = (
    STOCKTAKE_STATUS_COUNTING,
    STOCKTAKE_STATUS_CONFIRMED,
    STOCKTAKE_STATUS_CANCELLED,
)

STOCKTAKE_STATUS_LABELS: dict[str, str] = {
    STOCKTAKE_STATUS_COUNTING: "盘点中",
    STOCKTAKE_STATUS_CONFIRMED: "已确认",
    STOCKTAKE_STATUS_CANCELLED: "已取消",
}


class Stocktake(Base):
    """盘点单主表，对应 stocktakes。"""

    __tablename__ = "stocktakes"

    id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        primary_key=True,
        autoincrement=True,
        comment="盘点单ID",
    )
    stocktake_no: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="盘点单号，全局唯一",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=STOCKTAKE_STATUS_COUNTING,
        index=True,
        comment="COUNTING / CONFIRMED / CANCELLED",
    )
    scope: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="盘点范围描述，例如“全部分类”或“分类 3：服装”",
    )
    operator: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="盘点人",
    )
    remark: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="备注",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="确认时间",
    )

    # 盘点明细。
    items: Mapped[list["StocktakeItem"]] = relationship(
        back_populates="stocktake",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<Stocktake id={self.id} no={self.stocktake_no!r} "
            f"status={self.status}>"
        )


class StocktakeItem(Base):
    """盘点明细表，对应 stocktake_items。"""

    __tablename__ = "stocktake_items"

    id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        primary_key=True,
        autoincrement=True,
        comment="盘点明细ID",
    )
    stocktake_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("stocktakes.id"),
        nullable=False,
        index=True,
        comment="盘点单ID",
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("products.id"),
        nullable=False,
        index=True,
        comment="商品ID",
    )
    sku: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="商品SKU快照",
    )
    product_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="商品名称快照",
    )
    expected_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="账面数量（创建盘点单时的库存快照）",
    )
    counted_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="实盘数量，未录入为空",
    )
    difference: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="差异 = 实盘 - 账面",
    )
    remark: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="备注",
    )

    # 所属盘点单。
    stocktake: Mapped["Stocktake"] = relationship(back_populates="items")
    # 对应商品，仅用于类型提示之外的场景。
    product: Mapped["Product"] = relationship()

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<StocktakeItem id={self.id} sku={self.sku!r} "
            f"expected={self.expected_quantity} counted={self.counted_quantity}>"
        )
