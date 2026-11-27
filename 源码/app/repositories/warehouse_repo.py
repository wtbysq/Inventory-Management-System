"""仓库与仓库库存数据访问层。

这个 Repository 承担了一个重要的“兼容职责”：
    老数据只有 products.quantity，没有仓库维度库存。
    第一次涉及某个商品的仓库业务时，需要把总库存合理地
    拆分到默认仓库，保证：

        products.quantity == sum(warehouse_stocks.quantity)

初始化规则:
    - 商品没有任何仓库库存记录时，默认仓库初始化为 products.quantity；
    - 商品在其他仓库已有库存时，默认仓库 = 总库存 - 其他仓库总和（不小于 0）；
    - 非默认仓库没有记录时，初始化为 0。
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientStockError
from app.models.product import Product
from app.models.warehouse import (
    DEFAULT_WAREHOUSE_CODE,
    DEFAULT_WAREHOUSE_NAME,
    Warehouse,
    WarehouseStock,
)


class WarehouseRepository:
    """warehouses / warehouse_stocks 的数据访问对象。"""

    def __init__(self, db: Session) -> None:
        """保存数据库 Session。"""
        self.db = db

    # ------------------------------------------------------------------
    # 仓库
    # ------------------------------------------------------------------
    def add(self, warehouse: Warehouse) -> Warehouse:
        """新增仓库并 flush 获取 ID。"""
        self.db.add(warehouse)
        self.db.flush()
        return warehouse

    def get_by_id(self, warehouse_id: int) -> Warehouse | None:
        """按主键查询仓库。"""
        return self.db.get(Warehouse, warehouse_id)

    def get_by_code(self, code: str) -> Warehouse | None:
        """按编码查询仓库，用于唯一性校验。"""
        stmt = select(Warehouse).where(Warehouse.code == code)
        return self.db.scalar(stmt)

    def list_all(self) -> list[Warehouse]:
        """查询全部仓库，默认仓库排在最前面。"""
        stmt = select(Warehouse).order_by(
            Warehouse.is_default.desc(),
            Warehouse.id.asc(),
        )
        return list(self.db.scalars(stmt).all())

    def get_or_create_default(self) -> Warehouse:
        """获取默认仓库，不存在时自动创建。

        演示项目为了简化，没有加分布式锁；
        默认仓库由启动初始化或第一次业务调用创建，重复创建会触发
        code 唯一约束，因此生产环境建议改为启动时显式初始化。
        """
        stmt = select(Warehouse).where(Warehouse.is_default.is_(True))
        warehouse = self.db.scalar(stmt)
        if warehouse is not None:
            return warehouse

        warehouse = self.get_by_code(DEFAULT_WAREHOUSE_CODE)
        if warehouse is None:
            warehouse = Warehouse(
                code=DEFAULT_WAREHOUSE_CODE,
                name=DEFAULT_WAREHOUSE_NAME,
                is_default=True,
            )
            self.db.add(warehouse)
            self.db.flush()
        else:
            warehouse.is_default = True
        return warehouse

    # ------------------------------------------------------------------
    # 仓库库存
    # ------------------------------------------------------------------
    def get_stock(
        self,
        warehouse_id: int,
        product_id: int,
    ) -> WarehouseStock | None:
        """查询某个仓库下某个商品的库存记录。"""
        stmt = select(WarehouseStock).where(
            WarehouseStock.warehouse_id == warehouse_id,
            WarehouseStock.product_id == product_id,
        )
        return self.db.scalar(stmt)

    def ensure_stock(
        self,
        warehouse_id: int,
        product: Product,
    ) -> WarehouseStock:
        """获取仓库库存，不存在时按初始化规则创建。"""
        stock = self.get_stock(warehouse_id, product.id)
        if stock is not None:
            return stock

        default_warehouse = self.get_or_create_default()

        if warehouse_id == default_warehouse.id:
            # 其他仓库已有的库存要从总库存里扣掉，剩下的才属于默认仓库。
            other_total = self.db.scalar(
                select(func.coalesce(func.sum(WarehouseStock.quantity), 0))
                .where(WarehouseStock.product_id == product.id)
                .where(WarehouseStock.warehouse_id != default_warehouse.id)
            )
            initial_quantity = max(
                int(product.quantity) - int(other_total or 0),
                0,
            )
        else:
            # 非默认仓库第一次出现，库存为 0，需要先调拨进来。
            initial_quantity = 0

        stock = WarehouseStock(
            warehouse_id=warehouse_id,
            product_id=product.id,
            quantity=initial_quantity,
        )
        self.db.add(stock)
        self.db.flush()
        return stock

    def ensure_default_stock(
        self,
        product: Product,
    ) -> tuple[Warehouse, WarehouseStock]:
        """获取默认仓库及其库存记录。"""
        default_warehouse = self.get_or_create_default()
        stock = self.ensure_stock(default_warehouse.id, product)
        return default_warehouse, stock

    def apply_default_delta(
        self,
        product: Product,
        delta: int,
        *,
        check_stock: bool = False,
    ) -> WarehouseStock:
        """在默认仓库上增加/减少库存。

        重要:
            必须在修改 `product.quantity` 之前调用，
            否则 `ensure_stock` 初始化时会用到已经变更的总库存。

        Args:
            product: 商品 ORM 对象（读取 quantity 作为总库存）。
            delta: 正数入库，负数出库。
            check_stock: 出库时是否校验默认仓库库存是否足够。
        """
        _, stock = self.ensure_default_stock(product)
        new_quantity = stock.quantity + delta

        if new_quantity < 0:
            if check_stock:
                raise InsufficientStockError(
                    f"商品 {product.sku} 默认仓库库存不足，"
                    f"当前 {stock.quantity}，需要 {-delta}"
                )
            # 理论上不应该发生，做兜底避免出现负库存。
            new_quantity = 0

        stock.quantity = new_quantity
        return stock

    def apply_total_delta(
        self,
        product: Product,
        delta: int,
    ) -> WarehouseStock:
        """调整总库存时同步所有仓库，保证两者始终一致。

        与 `apply_default_delta` 的区别:
            - 盘点可能一次扣掉大量库存，默认仓库不一定够；
            - 这里会先扣默认仓库，不够再按仓库 ID 顺序扣其他仓库，
              避免出现 “总库存已减少，但仓库库存没减” 的不一致。

        注意:
            和 apply_default_delta 一样，必须在修改 product.quantity 之前调用。
        """
        default_warehouse, default_stock = self.ensure_default_stock(product)

        if delta >= 0:
            default_stock.quantity += delta
            return default_stock

        remaining = -delta
        take = min(default_stock.quantity, remaining)
        default_stock.quantity -= take
        remaining -= take

        if remaining > 0:
            other_stocks = list(
                self.db.scalars(
                    select(WarehouseStock)
                    .where(
                        WarehouseStock.product_id == product.id,
                        WarehouseStock.warehouse_id != default_warehouse.id,
                        WarehouseStock.quantity > 0,
                    )
                    .order_by(WarehouseStock.id.asc())
                ).all()
            )
            for stock in other_stocks:
                take = min(stock.quantity, remaining)
                stock.quantity -= take
                remaining -= take
                if remaining <= 0:
                    break

        if remaining > 0:
            # 仓库库存之和小于总库存，说明历史数据不一致，拒绝继续扣减。
            raise InsufficientStockError(
                f"商品 {product.sku} 仓库库存数据不一致，"
                f"仍有 {remaining} 件无法扣减，请先盘点核对"
            )

        return default_stock
