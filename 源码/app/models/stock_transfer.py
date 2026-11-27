"""库存调拨 ORM 模型。

调拨 = 把商品从 A 仓库挪到 B 仓库：
    - products.quantity（总库存）不变；
    - warehouse_stocks 中 A 仓库减少、B 仓库增加；
    - 调拨单本身作为审计凭证。

为什么调拨不写 inventory_logs？
    inventory_logs 记录的是“总库存”变化（before_quantity / after_quantity），
    调拨前后总库存不变，写进去会让流水难以理解。
    仓库维度的变化由调拨单明细完整记录。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import BIGINT_UNSIGNED_ID

if TYPE_CHECKING:
    # 仅用于类型检查，避免运行时循环导入。
    from app.models.warehouse import Warehouse

# 调拨单状态：当前只有完成态，保留字段便于扩展“草稿/审批”流程。
TRANSFER_STATUS_COMPLETED = "COMPLETED"
TRANSFER_STATUS_CANCELLED = "CANCELLED"

TRANSFER_STATUSES: tuple[str, ...] = (
    TRANSFER_STATUS_COMPLETED,
    TRANSFER_STATUS_CANCELLED,
)

TRANSFER_STATUS_LABELS: dict[str, str] = {
    TRANSFER_STATUS_COMPLETED: "已完成",
    TRANSFER_STATUS_CANCELLED: "已取消",
}


class StockTransfer(Base):
    """调拨单主表，对应 stock_transfers。"""

    __tablename__ = "stock_transfers"

    id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        primary_key=True,
        autoincrement=True,
        comment="调拨单ID",
    )
    transfer_no: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="调拨单号，全局唯一",
    )
    from_warehouse_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("warehouses.id"),
        nullable=False,
        index=True,
        comment="调出仓库ID",
    )
    to_warehouse_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("warehouses.id"),
        nullable=False,
        index=True,
        comment="调入仓库ID",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=TRANSFER_STATUS_COMPLETED,
        index=True,
        comment="COMPLETED / CANCELLED",
    )
    operator: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="操作人",
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
        comment="调拨时间",
    )

    # 调拨明细。
    items: Mapped[list["StockTransferItem"]] = relationship(
        back_populates="transfer",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # 调出/调入仓库，便于返回前端展示名称。
    from_warehouse: Mapped["Warehouse"] = relationship(
        foreign_keys=[from_warehouse_id],
        lazy="joined",
    )
    to_warehouse: Mapped["Warehouse"] = relationship(
        foreign_keys=[to_warehouse_id],
        lazy="joined",
    )

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<StockTransfer id={self.id} no={self.transfer_no!r} "
            f"{self.from_warehouse_id}->{self.to_warehouse_id}>"
        )


class StockTransferItem(Base):
    """调拨明细表，对应 stock_transfer_items。"""

    __tablename__ = "stock_transfer_items"

    id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        primary_key=True,
        autoincrement=True,
        comment="调拨明细ID",
    )
    transfer_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("stock_transfers.id"),
        nullable=False,
        index=True,
        comment="调拨单ID",
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
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="调拨数量",
    )

    # 所属调拨单。
    transfer: Mapped["StockTransfer"] = relationship(back_populates="items")

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<StockTransferItem id={self.id} sku={self.sku!r} "
            f"quantity={self.quantity}>"
        )
