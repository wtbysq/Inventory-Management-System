"""出入库流水 ORM 模型。"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import BIGINT_ID

if TYPE_CHECKING:
    # 仅用于类型检查，避免运行时循环导入。
    from app.models.product import Product


class InventoryLog(Base):
    """对应数据库表 inventory_logs。

    每次入库或出库都会生成一条流水，便于追溯库存变化。
    """

    __tablename__ = "inventory_logs"

    id: Mapped[int] = mapped_column(
        BIGINT_ID,
        primary_key=True,
        autoincrement=True,
        comment="流水ID",
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT_ID,
        ForeignKey("products.id"),
        nullable=False,
        index=True,
        comment="商品ID",
    )
    # 早期版本使用 MySQL ENUM('IN','OUT')，
    # 盘点(ADJUST)和调拨(TRANSFER_*)需要更多类型，
    # 因此改为 VARCHAR(16)，避免每次扩展都要改 ENUM 定义。
    # 取值：IN / OUT / ADJUST / TRANSFER_IN / TRANSFER_OUT
    change_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
        comment="IN 入库，OUT 出库，ADJUST 盘点调整",
    )
    change_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="本次变动数量，始终为正数",
    )

    before_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="变动前库存",
    )
    after_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="变动后库存",
    )

    operated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="操作时间",
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

    # 流水所属商品。
    product: Mapped["Product"] = relationship(
        back_populates="inventory_logs",
    )

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<InventoryLog id={self.id} product_id={self.product_id} "
            f"type={self.change_type} quantity={self.change_quantity}>"
        )
