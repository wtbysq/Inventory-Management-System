"""库存盘点数据访问层。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.stocktake import Stocktake


class StocktakeRepository:
    """stocktakes / stocktake_items 的数据访问对象。"""

    def __init__(self, db: Session) -> None:
        """保存数据库 Session。"""
        self.db = db

    def add(self, stocktake: Stocktake) -> Stocktake:
        """新增盘点单并 flush 获取 ID。"""
        self.db.add(stocktake)
        self.db.flush()
        return stocktake

    def get_by_id(self, stocktake_id: int) -> Stocktake | None:
        """按主键查询盘点单。"""
        return self.db.get(Stocktake, stocktake_id)

    def get_for_update(self, stocktake_id: int) -> Stocktake | None:
        """锁定盘点单，防止同一张盘点单被并发确认两次。"""
        stmt = (
            select(Stocktake)
            .where(Stocktake.id == stocktake_id)
            .with_for_update()
        )
        return self.db.scalar(stmt)

    def list_stocktakes(
        self,
        *,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Stocktake], int]:
        """分页查询盘点单。"""
        base_stmt = select(Stocktake)
        if status:
            base_stmt = base_stmt.where(Stocktake.status == status)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = int(self.db.scalar(count_stmt) or 0)

        items_stmt = (
            base_stmt.order_by(Stocktake.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(self.db.scalars(items_stmt).all()), total
