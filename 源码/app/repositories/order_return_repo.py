"""订单退货数据访问层。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order_return import OrderReturn


class OrderReturnRepository:
    """order_returns 表的数据访问对象。"""

    def __init__(self, db: Session) -> None:
        """保存数据库 Session。"""
        self.db = db

    def add(self, order_return: OrderReturn) -> OrderReturn:
        """新增退货单并 flush 获取 ID。"""
        self.db.add(order_return)
        self.db.flush()
        return order_return

    def get_by_id(self, return_id: int) -> OrderReturn | None:
        """按主键查询退货单。"""
        return self.db.get(OrderReturn, return_id)

    def list_by_order(self, order_id: int) -> list[OrderReturn]:
        """查询某个订单的全部退货单，按创建时间正序。"""
        stmt = (
            select(OrderReturn)
            .where(OrderReturn.order_id == order_id)
            .order_by(OrderReturn.id.asc())
        )
        return list(self.db.scalars(stmt).all())
