"""订单数据访问层。"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import (
    ORDER_STATUS_PAID,
    ORDER_STATUS_PARTIALLY_RETURNED,
    ORDER_STATUS_RETURNED,
    Order,
    OrderItem,
)
from app.models.product import Product

# 这些状态的订单已经收钱，计入营业额与利润。
PAID_STATUSES: tuple[str, ...] = (
    ORDER_STATUS_PAID,
    ORDER_STATUS_PARTIALLY_RETURNED,
    ORDER_STATUS_RETURNED,
)


def _to_money(value: object) -> Decimal:
    """把数据库聚合结果统一转成保留两位小数的 Decimal。"""
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


class OrderRepository:
    """订单表的数据访问对象。"""

    def __init__(self, db: Session) -> None:
        """保存数据库 Session。"""
        self.db = db

    def add(self, order: Order) -> Order:
        """新增订单并 flush 获取自增 ID。

        这里不 commit，事务边界由 OrderService 控制。
        """
        self.db.add(order)
        self.db.flush()
        return order

    def get_by_id(self, order_id: int) -> Order | None:
        """根据订单 ID 查询订单，不存在时返回 None。"""
        return self.db.get(Order, order_id)

    def get_for_update(self, order_id: int) -> Order | None:
        """锁定订单行，用于支付/取消/退货等状态变更。

        MySQL InnoDB 下生成 SELECT ... FOR UPDATE，
        防止两个请求同时支付同一订单或重复退货。
        """
        stmt = (
            select(Order)
            .where(Order.id == order_id)
            .with_for_update()
        )
        return self.db.scalar(stmt)

    def list_orders(
        self,
        *,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Order], int]:
        """分页查询订单。

        Args:
            status: 订单状态筛选，例如 CREATED。
            keyword: 订单号模糊搜索。
            page: 页码，从 1 开始。
            size: 每页数量。

        Returns:
            (当前页订单列表, 总记录数)
        """
        base_stmt = select(Order)

        if status:
            base_stmt = base_stmt.where(Order.status == status)

        if keyword:
            base_stmt = base_stmt.where(
                Order.order_no.like(f"%{keyword}%")
            )

        count_stmt = select(func.count()).select_from(
            base_stmt.subquery()
        )
        total = int(self.db.scalar(count_stmt) or 0)

        items_stmt = (
            base_stmt
            .order_by(Order.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = list(self.db.scalars(items_stmt).all())

        return items, total

    def stats(self) -> tuple[Decimal, int, Decimal]:
        """统计已支付订单的销售额、订单数和利润。

        利润按 (售价 - 商品当前成本价) × 未退货数量 汇总，
        已退货部分不计入；成本价为空时按 0 处理。

        Returns:
            (销售总额, 已支付订单数, 累计利润)
        """
        revenue_stmt = select(
            func.coalesce(
                func.sum(Order.total_amount - Order.refunded_amount),
                0,
            ),
            func.count(Order.id),
        ).where(Order.status.in_(PAID_STATUSES))
        revenue_row = self.db.execute(revenue_stmt).one()

        profit_stmt = (
            select(
                func.coalesce(
                    func.sum(
                        (OrderItem.unit_price - func.coalesce(Product.cost, 0))
                        * (OrderItem.quantity - OrderItem.returned_quantity)
                    ),
                    0,
                )
            )
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(Order.status.in_(PAID_STATUSES))
        )
        profit = self.db.scalar(profit_stmt)

        # SQLite 下 SUM(Numeric) 会返回 float，统一转成保留两位小数的 Decimal。
        return (
            _to_money(revenue_row[0]),
            int(revenue_row[1] or 0),
            _to_money(profit),
        )
