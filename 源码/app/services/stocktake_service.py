"""库存盘点业务逻辑。

盘点单生命周期:
    COUNTING（盘点中）
        -> CONFIRMED（已确认，库存已按实盘数量修正）
        -> CANCELLED（已取消，不影响库存）

确认盘点时会:
    1. 按商品 ID 顺序锁定商品行，避免与其他出入库交叉死锁；
    2. 把商品库存直接改成实盘数量；
    3. 差异同步到默认仓库库存；
    4. 为每个有差异的商品写一条 ADJUST 类型的库存流水。
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.cache import CACHE_KEY_PRODUCT_STATS, cache
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.inventory_log import InventoryLog
from app.models.stocktake import (
    STOCKTAKE_STATUS_CANCELLED,
    STOCKTAKE_STATUS_CONFIRMED,
    STOCKTAKE_STATUS_COUNTING,
    Stocktake,
    StocktakeItem,
)
from app.repositories.product_repo import ProductRepository
from app.repositories.stocktake_repo import StocktakeRepository
from app.repositories.warehouse_repo import WarehouseRepository


class StocktakeService:
    """盘点单创建、录入实盘数量、确认与查询。"""

    def __init__(self, db: Session) -> None:
        """初始化盘点 Service。"""
        self.db = db
        self.stocktake_repo = StocktakeRepository(db)
        self.product_repo = ProductRepository(db)
        self.warehouse_repo = WarehouseRepository(db)

    def create_stocktake(
        self,
        *,
        category_id: int | None = None,
        product_ids: list[int] | None = None,
        operator: str | None = None,
        remark: str | None = None,
    ) -> Stocktake:
        """创建盘点单，并把当前库存抄成账面数量。

        Raises:
            ValidationError: 没有可盘点的商品。
        """
        products = self.product_repo.list_for_stocktake(
            category_id=category_id,
            product_ids=product_ids,
        )
        if not products:
            raise ValidationError("没有找到需要盘点的商品")

        if product_ids:
            scope = f"指定商品 {len(products)} 个"
        elif category_id is not None:
            scope = f"分类 {category_id}"
        else:
            scope = "全部分类"

        now = datetime.now()
        stocktake = Stocktake(
            stocktake_no=f"ST{now:%Y%m%d%H%M%S}{uuid4().hex[:6].upper()}",
            status=STOCKTAKE_STATUS_COUNTING,
            scope=scope,
            operator=operator,
            remark=remark,
            created_at=now,
        )

        # 创建时的库存快照，后续确认盘点时用于计算差异。
        for product in products:
            stocktake.items.append(
                StocktakeItem(
                    product_id=product.id,
                    sku=product.sku,
                    product_name=product.product_name,
                    expected_quantity=product.quantity,
                )
            )

        self.db.add(stocktake)
        self.db.commit()
        return stocktake

    def count_items(
        self,
        stocktake_id: int,
        *,
        items: list[dict],
    ) -> Stocktake:
        """批量录入实盘数量。

        Args:
            items: [{"product_id": 1, "counted_quantity": 8, "remark": "..."}]
        """
        stocktake = self.stocktake_repo.get_for_update(stocktake_id)
        if stocktake is None:
            raise NotFoundError(f"盘点单不存在: id={stocktake_id}")
        if stocktake.status != STOCKTAKE_STATUS_COUNTING:
            raise ConflictError(
                f"盘点单当前状态为 {stocktake.status}，不允许录入"
            )

        # 只允许录入本盘点单包含的商品。
        item_map = {item.product_id: item for item in stocktake.items}

        for row in items:
            product_id = int(row["product_id"])
            counted_quantity = int(row["counted_quantity"])

            if counted_quantity < 0:
                raise ValidationError("实盘数量不能为负数")

            item = item_map.get(product_id)
            if item is None:
                raise NotFoundError(
                    f"商品不在本盘点单中: id={product_id}"
                )

            item.counted_quantity = counted_quantity
            # 差异基于“创建盘点单时的账面数”计算。
            item.difference = counted_quantity - item.expected_quantity
            if "remark" in row:
                item.remark = row["remark"]

        self.db.commit()
        return stocktake

    def confirm_stocktake(
        self,
        stocktake_id: int,
        *,
        operator: str | None = None,
    ) -> Stocktake:
        """确认盘点，按实盘数量修正库存。

        未录入实盘数量的商品会被跳过（视为无差异），
        这样支持“只盘部分商品”的场景。
        """
        now = datetime.now()

        try:
            stocktake = self.stocktake_repo.get_for_update(stocktake_id)
            if stocktake is None:
                raise NotFoundError(f"盘点单不存在: id={stocktake_id}")
            if stocktake.status != STOCKTAKE_STATUS_COUNTING:
                raise ConflictError(
                    f"盘点单当前状态为 {stocktake.status}，不允许确认"
                )

            # 按商品 ID 排序加锁，保持和其他库存事务一致的加锁顺序。
            for item in sorted(stocktake.items, key=lambda row: row.product_id):
                if item.counted_quantity is None:
                    continue

                product = self.product_repo.get_for_update(item.product_id)
                if product is None:
                    raise NotFoundError(
                        f"商品不存在: id={item.product_id}"
                    )

                before_quantity = product.quantity
                after_quantity = item.counted_quantity
                delta = after_quantity - before_quantity

                # 差异为 0 时不需要改库存，但差异字段仍要记录。
                item.difference = after_quantity - item.expected_quantity

                if delta == 0:
                    continue

                # 同步仓库库存：
                # 盘盈加到默认仓库；盘亏先扣默认仓库，不够再扣其他仓库，
                # 保证 products.quantity 与仓库库存之和一致。
                self.warehouse_repo.apply_total_delta(product, delta)

                product.quantity = after_quantity
                if delta > 0:
                    product.last_inbound_at = now
                else:
                    product.last_outbound_at = now

                self.db.add(
                    InventoryLog(
                        product_id=product.id,
                        change_type="ADJUST",
                        change_quantity=abs(delta),
                        before_quantity=before_quantity,
                        after_quantity=after_quantity,
                        operated_at=now,
                        operator=operator,
                        remark=(
                            f"盘点调整 {stocktake.stocktake_no}"
                            f"（账面 {item.expected_quantity}）"
                        ),
                    )
                )

            stocktake.status = STOCKTAKE_STATUS_CONFIRMED
            stocktake.confirmed_at = now
            if operator:
                stocktake.operator = operator

            self.db.commit()
            cache.delete(CACHE_KEY_PRODUCT_STATS)
            return stocktake

        except Exception:
            self.db.rollback()
            raise

    def cancel_stocktake(self, stocktake_id: int) -> Stocktake:
        """取消盘点单，不影响库存。"""
        stocktake = self.stocktake_repo.get_by_id(stocktake_id)
        if stocktake is None:
            raise NotFoundError(f"盘点单不存在: id={stocktake_id}")
        if stocktake.status == STOCKTAKE_STATUS_CONFIRMED:
            raise ConflictError("已确认的盘点单不能取消")
        if stocktake.status == STOCKTAKE_STATUS_CANCELLED:
            raise ConflictError("盘点单已经取消")

        stocktake.status = STOCKTAKE_STATUS_CANCELLED
        self.db.commit()
        return stocktake

    def get_stocktake(self, stocktake_id: int) -> Stocktake:
        """查询盘点单详情。"""
        stocktake = self.stocktake_repo.get_by_id(stocktake_id)
        if stocktake is None:
            raise NotFoundError(f"盘点单不存在: id={stocktake_id}")
        return stocktake

    def list_stocktakes(
        self,
        *,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Stocktake], int]:
        """分页查询盘点单。"""
        return self.stocktake_repo.list_stocktakes(
            status=status,
            page=page,
            size=size,
        )
