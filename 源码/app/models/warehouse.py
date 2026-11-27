"""仓库与仓库库存 ORM 模型。

为什么要引入仓库？
    库存调拨（transfer）本质是“把同一个商品的库存从 A 仓库挪到 B 仓库”。
    如果只有一个 products.quantity 字段，调拨就无法表达。

数据关系:
    products.quantity            = 所有仓库库存之和（总库存）
    warehouse_stocks.quantity    = 某个仓库下某个商品的库存

约定:
    - 默认仓库 code = MAIN，应用启动后第一次使用时自动创建。
    - 存量商品第一次参与仓库业务时，会自动把 products.quantity
      作为默认仓库库存初始化，保证历史数据兼容。
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import BIGINT_UNSIGNED_ID

# 默认仓库编码与名称。
DEFAULT_WAREHOUSE_CODE = "MAIN"
DEFAULT_WAREHOUSE_NAME = "主仓库"


class Warehouse(Base):
    """对应数据库表 warehouses。"""

    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        primary_key=True,
        autoincrement=True,
        comment="仓库ID",
    )
    code: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
        comment="仓库编码，例如 MAIN、WH-SH",
    )
    name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="仓库名称",
    )
    address: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="仓库地址",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否为默认仓库，出入库默认操作该仓库",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )

    # 该仓库下的商品库存。
    stocks: Mapped[list["WarehouseStock"]] = relationship(
        back_populates="warehouse",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return f"<Warehouse id={self.id} code={self.code!r} name={self.name!r}>"


class WarehouseStock(Base):
    """对应数据库表 warehouse_stocks：仓库维度库存。"""

    __tablename__ = "warehouse_stocks"
    __table_args__ = (
        # 同一个仓库下的同一个商品只能有一条库存记录。
        UniqueConstraint(
            "warehouse_id",
            "product_id",
            name="uk_warehouse_product",
        ),
    )

    id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        primary_key=True,
        autoincrement=True,
        comment="库存记录ID",
    )
    warehouse_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("warehouses.id"),
        nullable=False,
        index=True,
        comment="仓库ID",
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        ForeignKey("products.id"),
        nullable=False,
        index=True,
        comment="商品ID",
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="该仓库下的库存数量",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )

    # 所属仓库。
    warehouse: Mapped["Warehouse"] = relationship(back_populates="stocks")

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<WarehouseStock warehouse={self.warehouse_id} "
            f"product={self.product_id} quantity={self.quantity}>"
        )
