"""库存业务逻辑层。

核心职责:
    - 入库增加库存
    - 出库扣减库存，并防止库存变成负数
    - 每次变动写入 inventory_logs 流水
    - 同步维护默认仓库库存（warehouse_stocks）
    - 使用数据库事务保证库存与流水一致
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.cache import CACHE_KEY_PRODUCT_STATS, cache
from app.core.exceptions import (
    InsufficientStockError,
    NotFoundError,
    ValidationError,
)
from app.models.inventory_log import InventoryLog
from app.repositories.inventory_log_repo import InventoryLogRepository
from app.repositories.product_repo import ProductRepository
from app.repositories.warehouse_repo import WarehouseRepository


class InventoryService:
    """库存出入库业务。"""

    def __init__(self, db: Session) -> None:
        """初始化库存 Service。"""
        self.db = db
        self.product_repo = ProductRepository(db)
        self.log_repo = InventoryLogRepository(db)
        self.warehouse_repo = WarehouseRepository(db)

    def inbound(
        self,
        *,
        product_id: int,
        quantity: int,
        operator: str | None = None,
        remark: str | None = None,
    ) -> InventoryLog:
        """商品入库。

        Args:
            product_id: 商品 ID。
            quantity: 入库数量，必须大于 0。
            operator: 操作人。
            remark: 备注。

        Returns:
            新生成的库存流水。
        """
        return self._change_stock(
            product_id=product_id,
            quantity=quantity,
            change_type="IN",
            operator=operator,
            remark=remark,
        )

    def outbound(
        self,
        *,
        product_id: int,
        quantity: int,
        operator: str | None = None,
        remark: str | None = None,
    ) -> InventoryLog:
        """商品出库。

        出库前会锁定商品行并检查库存，库存不足时抛出异常，
        整个事务回滚，商品库存和流水都不会发生变化。

        Args:
            product_id: 商品 ID。
            quantity: 出库数量，必须大于 0。
            operator: 操作人。
            remark: 备注。

        Returns:
            新生成的库存流水。

        Raises:
            NotFoundError: 商品不存在。
            InsufficientStockError: 库存不足。
        """
        return self._change_stock(
            product_id=product_id,
            quantity=quantity,
            change_type="OUT",
            operator=operator,
            remark=remark,
        )

    def list_logs(
        self,
        *,
        product_id: int | None = None,
        change_type: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[InventoryLog], int]:
        """分页查询库存流水。"""
        return self.log_repo.list_logs(
            product_id=product_id,
            change_type=change_type,
            page=page,
            size=size,
        )

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _change_stock(
        self,
        *,
        product_id: int,
        quantity: int,
        change_type: str,
        operator: str | None,
        remark: str | None,
    ) -> InventoryLog:
        """入库/出库的公共实现。

        事务流程:
            1. 查询商品并加行锁
            2. 获取/初始化默认仓库库存
            3. 计算变动前后库存（出库时校验）
            4. 更新商品总库存和默认仓库库存
            5. 写入库存流水
            6. 提交事务并清理统计缓存

        任意一步失败都会回滚，保证库存和流水一致。
        """
        if quantity <= 0:
            raise ValidationError("出入库数量必须大于 0")

        now = datetime.now()

        try:
            # with_for_update 会在 MySQL InnoDB 中锁定该商品行，
            # 防止两个请求同时出库导致库存被扣成负数。
            product = self.product_repo.get_for_update(product_id)
            if product is None:
                raise NotFoundError(f"商品不存在: id={product_id}")

            # 先确保默认仓库库存记录存在。
            # 老数据没有仓库库存，这里会按“总库存”自动初始化。
            _, default_stock = self.warehouse_repo.ensure_default_stock(product)

            before_quantity = product.quantity

            if change_type == "IN":
                after_quantity = before_quantity + quantity
                product.last_inbound_at = now
                delta = quantity
            else:
                if before_quantity < quantity:
                    raise InsufficientStockError(
                        f"商品 {product.sku} 库存不足，"
                        f"当前库存 {before_quantity}，需要 {quantity}"
                    )
                if default_stock.quantity < quantity:
                    raise InsufficientStockError(
                        f"商品 {product.sku} 默认仓库库存不足，"
                        f"当前 {default_stock.quantity}，需要 {quantity}；"
                        "请先从其他仓库调拨"
                    )
                after_quantity = before_quantity - quantity
                product.last_outbound_at = now
                delta = -quantity

            # 更新商品总库存与默认仓库库存。
            product.quantity = after_quantity
            default_stock.quantity += delta

            # 写入库存流水，便于后续审计和追溯。
            log = InventoryLog(
                product_id=product.id,
                change_type=change_type,
                change_quantity=quantity,
                before_quantity=before_quantity,
                after_quantity=after_quantity,
                operated_at=now,
                operator=operator,
                remark=remark,
            )
            self.db.add(log)

            # 提交事务：商品库存、仓库库存和库存流水同时生效。
            self.db.commit()
            cache.delete(CACHE_KEY_PRODUCT_STATS)
            return log

        except Exception:
            # 任意异常都回滚，避免出现“库存扣了但流水没写”的情况。
            self.db.rollback()
            raise
