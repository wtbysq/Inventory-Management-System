"""仓库管理与库存调拨业务逻辑。

调拨核心:
    1. 校验调出/调入仓库存在且不相同；
    2. 按商品 ID 顺序锁定商品行（防止与其他库存事务死锁）；
    3. 校验调出仓库库存是否足够；
    4. 调出仓库减少、调入仓库增加，总库存 products.quantity 不变；
    5. 生成调拨单和明细作为审计凭证。

与出入库的区别:
    调拨不改变总库存，因此不写 inventory_logs，
    仓库维度变化通过调拨单明细追溯。
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    InsufficientStockError,
    NotFoundError,
    ValidationError,
)
from app.models.stock_transfer import (
    TRANSFER_STATUS_COMPLETED,
    StockTransfer,
    StockTransferItem,
)
from app.models.warehouse import Warehouse
from app.repositories.product_repo import ProductRepository
from app.repositories.transfer_repo import TransferRepository
from app.repositories.warehouse_repo import WarehouseRepository
from app.schemas.transfer import TransferItemCreate


class WarehouseService:
    """仓库查询与创建。"""

    def __init__(self, db: Session) -> None:
        """初始化仓库 Service。"""
        self.db = db
        self.warehouse_repo = WarehouseRepository(db)

    def list_warehouses(self) -> list[Warehouse]:
        """查询全部仓库。

        首次调用时自动创建默认仓库，保证前端下拉框不为空。
        """
        self.warehouse_repo.get_or_create_default()
        self.db.commit()
        return self.warehouse_repo.list_all()

    def create_warehouse(
        self,
        *,
        code: str,
        name: str,
        address: str | None = None,
    ) -> Warehouse:
        """创建仓库。

        Raises:
            ConflictError: 仓库编码重复。
        """
        code = code.strip().upper()
        if self.warehouse_repo.get_by_code(code) is not None:
            raise ConflictError(f"仓库编码已存在: {code}")

        warehouse = Warehouse(
            code=code,
            name=name.strip(),
            address=address,
            is_default=False,
        )
        self.warehouse_repo.add(warehouse)
        self.db.commit()
        return warehouse


class TransferService:
    """库存调拨业务。"""

    def __init__(self, db: Session) -> None:
        """初始化调拨 Service。"""
        self.db = db
        self.transfer_repo = TransferRepository(db)
        self.warehouse_repo = WarehouseRepository(db)
        self.product_repo = ProductRepository(db)

    def create_transfer(
        self,
        *,
        from_warehouse_id: int,
        to_warehouse_id: int,
        items: list[TransferItemCreate],
        operator: str | None = None,
        remark: str | None = None,
    ) -> StockTransfer:
        """创建并立即完成一张调拨单。

        Raises:
            ValidationError: 调出调入仓库相同或明细为空。
            NotFoundError: 仓库或商品不存在。
            InsufficientStockError: 调出仓库库存不足。
        """
        if from_warehouse_id == to_warehouse_id:
            raise ValidationError("调出仓库和调入仓库不能相同")

        if not items:
            raise ValidationError("调拨单至少需要包含一个商品")

        from_warehouse = self.warehouse_repo.get_by_id(from_warehouse_id)
        if from_warehouse is None:
            raise NotFoundError(f"调出仓库不存在: id={from_warehouse_id}")

        to_warehouse = self.warehouse_repo.get_by_id(to_warehouse_id)
        if to_warehouse is None:
            raise NotFoundError(f"调入仓库不存在: id={to_warehouse_id}")

        # 合并同一商品的重复行。
        merged_items: dict[int, int] = {}
        for item in items:
            if item.quantity <= 0:
                raise ValidationError("调拨数量必须大于 0")
            merged_items[item.product_id] = (
                merged_items.get(item.product_id, 0) + item.quantity
            )

        now = datetime.now()

        try:
            transfer = StockTransfer(
                transfer_no=f"TR{now:%Y%m%d%H%M%S}{uuid4().hex[:6].upper()}",
                from_warehouse_id=from_warehouse.id,
                to_warehouse_id=to_warehouse.id,
                status=TRANSFER_STATUS_COMPLETED,
                operator=operator,
                remark=remark,
                created_at=now,
            )
            self.db.add(transfer)
            self.db.flush()

            for product_id in sorted(merged_items):
                quantity = merged_items[product_id]

                product = self.product_repo.get_for_update(product_id)
                if product is None:
                    raise NotFoundError(f"商品不存在: id={product_id}")

                from_stock = self.warehouse_repo.ensure_stock(
                    from_warehouse.id,
                    product,
                )
                to_stock = self.warehouse_repo.ensure_stock(
                    to_warehouse.id,
                    product,
                )

                if from_stock.quantity < quantity:
                    raise InsufficientStockError(
                        f"仓库 {from_warehouse.name} 商品 {product.sku} "
                        f"库存不足，当前 {from_stock.quantity}，需要 {quantity}"
                    )

                # 一减一增，总库存保持不变。
                from_stock.quantity -= quantity
                to_stock.quantity += quantity

                transfer.items.append(
                    StockTransferItem(
                        product_id=product.id,
                        sku=product.sku,
                        product_name=product.product_name,
                        quantity=quantity,
                    )
                )

            self.db.commit()
            return transfer

        except Exception:
            self.db.rollback()
            raise

    def get_transfer(self, transfer_id: int) -> StockTransfer:
        """查询调拨单详情。"""
        transfer = self.transfer_repo.get_by_id(transfer_id)
        if transfer is None:
            raise NotFoundError(f"调拨单不存在: id={transfer_id}")
        return transfer

    def list_transfers(
        self,
        *,
        warehouse_id: int | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[StockTransfer], int]:
        """分页查询调拨单，可按仓库过滤。"""
        return self.transfer_repo.list_transfers(
            warehouse_id=warehouse_id,
            page=page,
            size=size,
        )
