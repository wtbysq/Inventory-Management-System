"""出入库流水数据访问层。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inventory_log import InventoryLog


class InventoryLogRepository:
    """库存流水表的数据访问对象。"""

    def __init__(self, db: Session) -> None:
        """保存数据库 Session。"""
        self.db = db

    def create(self, log: InventoryLog) -> InventoryLog:
        """新增一条库存流水。

        使用 flush 而不是 commit，让 Service 层统一控制事务边界。
        """
        self.db.add(log)
        self.db.flush()
        return log

    def list_logs(
        self,
        *,
        product_id: int | None = None,
        change_type: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[InventoryLog], int]:
        """分页查询库存流水。

        Args:
            product_id: 只查询某个商品的流水，None 表示全部。
            change_type: 只查询某种类型（IN/OUT/ADJUST），None 表示全部。
            page: 页码，从 1 开始。
            size: 每页数量。

        Returns:
            (当前页流水列表, 总记录数)
        """
        base_stmt = select(InventoryLog)

        if product_id is not None:
            base_stmt = base_stmt.where(
                InventoryLog.product_id == product_id
            )
        if change_type:
            base_stmt = base_stmt.where(
                InventoryLog.change_type == change_type
            )

        count_stmt = select(func.count()).select_from(
            base_stmt.subquery()
        )
        total = int(self.db.scalar(count_stmt) or 0)

        items_stmt = (
            base_stmt
            .order_by(InventoryLog.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = list(self.db.scalars(items_stmt).all())

        return items, total
