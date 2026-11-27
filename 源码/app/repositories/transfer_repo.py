"""库存调拨数据访问层。"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.stock_transfer import StockTransfer


class TransferRepository:
    """stock_transfers / stock_transfer_items 的数据访问对象。"""

    def __init__(self, db: Session) -> None:
        """保存数据库 Session。"""
        self.db = db

    def add(self, transfer: StockTransfer) -> StockTransfer:
        """新增调拨单并 flush 获取 ID。"""
        self.db.add(transfer)
        self.db.flush()
        return transfer

    def get_by_id(self, transfer_id: int) -> StockTransfer | None:
        """按主键查询调拨单。"""
        return self.db.get(StockTransfer, transfer_id)

    def list_transfers(
        self,
        *,
        warehouse_id: int | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[StockTransfer], int]:
        """分页查询调拨单，可按仓库（调入或调出）过滤。"""
        base_stmt = select(StockTransfer)

        if warehouse_id is not None:
            base_stmt = base_stmt.where(
                or_(
                    StockTransfer.from_warehouse_id == warehouse_id,
                    StockTransfer.to_warehouse_id == warehouse_id,
                )
            )

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = int(self.db.scalar(count_stmt) or 0)

        items_stmt = (
            base_stmt.order_by(StockTransfer.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(self.db.scalars(items_stmt).all()), total
