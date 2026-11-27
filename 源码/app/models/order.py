"""订单与订单明细 ORM 模型。

订单状态流转:
    CREATED --支付--> PAID --退货--> PARTIALLY_RETURNED / RETURNED
    CREATED --取消--> CANCELLED（回补库存）

说明:
    - PAID 的订单不允许直接取消，只能走退货流程（钱已经收了）；
    - 每退一次货生成一张退货单，订单上的 refunded_amount 累计退款金额；
    - 订单明细上的 returned_quantity 记录累计已退数量。
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
    from app.models.order_return import OrderReturn
    from app.models.product import Product

# ----------------------------------------------------------------------
# 订单状态常量
# ----------------------------------------------------------------------
ORDER_STATUS_CREATED = "CREATED"
ORDER_STATUS_PAID = "PAID"
ORDER_STATUS_CANCELLED = "CANCELLED"
ORDER_STATUS_PARTIALLY_RETURNED = "PARTIALLY_RETURNED"
ORDER_STATUS_RETURNED = "RETURNED"

ORDER_STATUSES: tuple[str, ...] = (
    ORDER_STATUS_CREATED,
    ORDER_STATUS_PAID,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_PARTIALLY_RETURNED,
    ORDER_STATUS_RETURNED,
)

ORDER_STATUS_LABELS: dict[str, str] = {
    ORDER_STATUS_CREATED: "已创建",
    ORDER_STATUS_PAID: "已支付",
    ORDER_STATUS_CANCELLED: "已取消",
    ORDER_STATUS_PARTIALLY_RETURNED: "部分退货",
    ORDER_STATUS_RETURNED: "已退货",
}


class Order(Base):
    """订单主表，对应 orders 表。

    一个订单可以包含多个商品，每个商品对应一条 OrderItem。
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        primary_key=True,
        autoincrement=True,
        comment="订单ID",
    )
    order_no: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="订单号，全局唯一",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="订单总金额",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ORDER_STATUS_CREATED,
        index=True,
        comment="CREATED/PAID/CANCELLED/PARTIALLY_RETURNED/RETURNED",
    )
    operator: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="下单人",
    )
    remark: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="订单备注",
    )

    # ------------------------------------------------------------------
    # 支付信息
    # ------------------------------------------------------------------
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="支付时间",
    )
    payment_method: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="支付方式，例如 BALANCE / WECHAT / ALIPAY",
    )

    # ------------------------------------------------------------------
    # 取消信息
    # ------------------------------------------------------------------
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="取消时间",
    )
    cancel_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="取消原因",
    )

    # ------------------------------------------------------------------
    # 退货信息
    # ------------------------------------------------------------------
    refunded_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="累计已退款金额",
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

    # 订单明细。
    # lazy="selectin" 表示查询订单时自动批量加载明细，
    # 避免返回订单列表时产生 N+1 查询。
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # 该订单的所有退货单，同样批量加载避免 N+1 查询。
    returns: Mapped[list["OrderReturn"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<Order id={self.id} order_no={self.order_no!r} "
            f"amount={self.total_amount}>"
        )


class OrderItem(Base):
    """订单明细表，对应 order_items 表。

    商品名称、SKU、单价都会保存快照，
    这样即使商品后续改名或改价，历史订单仍然可追溯。
    """

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        primary_key=True,
        autoincrement=True,
        comment="明细ID",
    )
    order_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("orders.id"),
        nullable=False,
        index=True,
        comment="订单ID",
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("products.id"),
        nullable=False,
        index=True,
        comment="商品ID",
    )

    # 以下字段是下单时的商品快照。
    product_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="下单时的商品名称",
    )
    sku: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="下单时的商品SKU",
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="购买数量",
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="下单时的单价",
    )
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="小计金额：unit_price * quantity",
    )
    returned_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="累计已退数量，用于控制最多可退数量",
    )

    # 明细所属订单。
    order: Mapped["Order"] = relationship(back_populates="items")
    # 明细对应商品，用于读取成本价计算订单利润。
    # lazy="selectin" 与 Order.items 保持一致，避免序列化时逐行查询。
    product: Mapped["Product"] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<OrderItem id={self.id} order_id={self.order_id} "
            f"sku={self.sku!r} quantity={self.quantity}>"
        )
