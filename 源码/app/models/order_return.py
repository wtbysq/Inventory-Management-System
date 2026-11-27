"""订单退货 ORM 模型。

为什么退货单独建表，而不是直接改订单状态？
    1. 一个订单可能分多次退货（部分退货），需要保留每次退货的数量、
       退款金额和原因；
    2. 退货是审计信息，不能因为后续订单状态变化而丢失；
    3. 订单明细上只记录“累计已退数量”，明细账在退货单里。

表关系:
    orders 1 --- n order_returns 1 --- n order_return_items
    order_items 1 --- n order_return_items（按订单明细退货）
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import BIGINT_UNSIGNED_ID

if TYPE_CHECKING:
    # 仅用于类型检查，避免运行时循环导入。
    from app.models.order import Order


class OrderReturn(Base):
    """退货单主表，对应 order_returns。"""

    __tablename__ = "order_returns"

    id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        primary_key=True,
        autoincrement=True,
        comment="退货单ID",
    )
    return_no: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="退货单号，全局唯一",
    )
    order_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("orders.id"),
        nullable=False,
        index=True,
        comment="原订单ID",
    )
    refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="本次退款金额",
    )
    reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="退货原因",
    )
    operator: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="操作人",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="退货时间",
    )

    # 退货明细，查询退货单时一次性加载。
    items: Mapped[list["OrderReturnItem"]] = relationship(
        back_populates="order_return",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # 所属订单。
    order: Mapped["Order"] = relationship(back_populates="returns")

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<OrderReturn id={self.id} return_no={self.return_no!r} "
            f"refund={self.refund_amount}>"
        )


class OrderReturnItem(Base):
    """退货明细表，对应 order_return_items。

    保存商品名称/SKU/单价的快照，保证历史可追溯。
    """

    __tablename__ = "order_return_items"

    id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        primary_key=True,
        autoincrement=True,
        comment="退货明细ID",
    )
    return_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("order_returns.id"),
        nullable=False,
        index=True,
        comment="退货单ID",
    )
    order_item_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("order_items.id"),
        nullable=False,
        index=True,
        comment="原订单明细ID",
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("products.id"),
        nullable=False,
        index=True,
        comment="商品ID",
    )
    product_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="商品名称快照",
    )
    sku: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="商品SKU快照",
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="退货数量",
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="下单时单价",
    )
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="退款小计",
    )

    # 所属退货单。
    order_return: Mapped["OrderReturn"] = relationship(
        back_populates="items",
    )

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<OrderReturnItem id={self.id} sku={self.sku!r} "
            f"quantity={self.quantity}>"
        )
