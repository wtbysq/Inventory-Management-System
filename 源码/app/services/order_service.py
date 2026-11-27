"""订单业务逻辑层。

核心流程:
    下单: 合并重复行 -> 锁定商品 -> 校验库存 -> 扣减总库存与默认仓库库存
          -> 写订单明细 -> 写出库流水 -> 提交
    支付: 锁定订单 -> CREATED -> PAID
    取消: 锁定订单 -> CREATED -> CANCELLED，并回补库存、写 IN 流水
    退货: 锁定订单 -> PAID/PARTIALLY_RETURNED -> 生成退货单
          -> 回补库存、写 IN 流水 -> 更新累计退款与订单状态

事务原则:
    所有步骤在同一个事务中完成，任意一步失败整单回滚。
"""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.cache import (
    CACHE_KEY_ORDER_STATS,
    CACHE_KEY_PRODUCT_STATS,
    cache,
)
from app.core.exceptions import (
    ConflictError,
    InsufficientStockError,
    NotFoundError,
    ValidationError,
)
from app.models.inventory_log import InventoryLog
from app.models.order import (
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_CREATED,
    ORDER_STATUS_PAID,
    ORDER_STATUS_PARTIALLY_RETURNED,
    ORDER_STATUS_RETURNED,
    Order,
    OrderItem,
)
from app.models.order_return import OrderReturn, OrderReturnItem
from app.repositories.order_repo import OrderRepository
from app.repositories.order_return_repo import OrderReturnRepository
from app.repositories.product_repo import ProductRepository
from app.repositories.warehouse_repo import WarehouseRepository
from app.schemas.order import OrderItemCreate, OrderReturnItemCreate, OrderStats


class OrderService:
    """订单创建、支付、取消、退货与查询。"""

    def __init__(self, db: Session) -> None:
        """初始化订单 Service。"""
        self.db = db
        self.order_repo = OrderRepository(db)
        self.order_return_repo = OrderReturnRepository(db)
        self.product_repo = ProductRepository(db)
        self.warehouse_repo = WarehouseRepository(db)

    # ------------------------------------------------------------------
    # 下单
    # ------------------------------------------------------------------
    def create_order(
        self,
        *,
        items: list[OrderItemCreate],
        operator: str | None = None,
        remark: str | None = None,
    ) -> Order:
        """创建订单并扣减库存。

        Args:
            items: 订单商品列表。
            operator: 下单人。
            remark: 订单备注。

        Returns:
            创建成功的订单，包含订单明细。

        Raises:
            ValidationError: 订单商品为空。
            NotFoundError: 商品不存在。
            InsufficientStockError: 任一商品库存不足。
        """
        if not items:
            raise ValidationError("订单至少需要包含一个商品")

        # 同一商品可能提交多行，先合并数量，避免重复加锁。
        merged_items: dict[int, int] = {}
        for item in items:
            merged_items[item.product_id] = (
                merged_items.get(item.product_id, 0) + item.quantity
            )

        now = datetime.now()
        order_no = f"SO{now:%Y%m%d%H%M%S}{uuid4().hex[:6].upper()}"

        try:
            # 先创建订单主记录，flush 后可以获得订单 ID。
            order = Order(
                order_no=order_no,
                total_amount=Decimal("0.00"),
                status=ORDER_STATUS_CREATED,
                operator=operator,
                remark=remark,
                created_at=now,
            )
            self.db.add(order)
            self.db.flush()

            total_amount = Decimal("0.00")

            # 按商品 ID 排序后加锁，降低多个订单交叉加锁导致死锁的概率。
            for product_id in sorted(merged_items):
                quantity = merged_items[product_id]

                # 锁定商品行，防止并发出库/下单造成超卖。
                product = self.product_repo.get_for_update(product_id)
                if product is None:
                    raise NotFoundError(f"商品不存在: id={product_id}")

                if product.quantity < quantity:
                    raise InsufficientStockError(
                        f"商品 {product.sku} 库存不足，"
                        f"当前库存 {product.quantity}，需要 {quantity}"
                    )

                # 同步扣减默认仓库库存。
                # 必须在修改 product.quantity 之前调用，内部会用它初始化仓库库存。
                self.warehouse_repo.apply_default_delta(
                    product,
                    -quantity,
                    check_stock=True,
                )

                unit_price = Decimal(str(product.price))
                subtotal = unit_price * quantity
                before_quantity = product.quantity
                after_quantity = before_quantity - quantity

                # 扣减库存并记录最近出库时间。
                product.quantity = after_quantity
                product.last_outbound_at = now

                # 写订单明细，保存商品名称/SKU/单价快照。
                order.items.append(
                    OrderItem(
                        product_id=product.id,
                        product_name=product.product_name,
                        sku=product.sku,
                        quantity=quantity,
                        unit_price=unit_price,
                        subtotal=subtotal,
                        returned_quantity=0,
                    )
                )

                # 每个商品生成一条出库流水，便于库存追溯。
                self.db.add(
                    InventoryLog(
                        product_id=product.id,
                        change_type="OUT",
                        change_quantity=quantity,
                        before_quantity=before_quantity,
                        after_quantity=after_quantity,
                        operated_at=now,
                        operator=operator,
                        remark=f"订单出库 {order_no}",
                    )
                )

                total_amount += subtotal

            order.total_amount = total_amount

            # 订单、明细、库存、流水在同一个事务中提交。
            self.db.commit()
            cache.delete(CACHE_KEY_PRODUCT_STATS)
            return order

        except Exception:
            # 任一商品失败时回滚整个订单。
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # 支付
    # ------------------------------------------------------------------
    def pay_order(
        self,
        order_id: int,
        *,
        payment_method: str = "BALANCE",
        operator: str | None = None,
    ) -> Order:
        """支付订单：CREATED -> PAID。

        说明:
            演示项目不接入真实支付渠道，只记录支付方式和时间。
            真实系统应在此处调用支付网关，并通过回调确认支付结果。

        Raises:
            NotFoundError: 订单不存在。
            ConflictError: 订单已支付或状态不允许支付。
        """
        try:
            order = self.order_repo.get_for_update(order_id)
            if order is None:
                raise NotFoundError(f"订单不存在: id={order_id}")

            if order.status == ORDER_STATUS_PAID:
                raise ConflictError("订单已经支付，请勿重复支付")
            if order.status != ORDER_STATUS_CREATED:
                raise ConflictError(
                    f"订单当前状态为 {order.status}，不允许支付"
                )

            order.status = ORDER_STATUS_PAID
            order.paid_at = datetime.now()
            order.payment_method = payment_method
            if operator:
                order.operator = operator

            self.db.commit()
            # 支付后订单统计（销售额/利润）发生变化。
            cache.delete(CACHE_KEY_ORDER_STATS)
            return order

        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # 取消
    # ------------------------------------------------------------------
    def cancel_order(
        self,
        order_id: int,
        *,
        reason: str | None = None,
        operator: str | None = None,
    ) -> Order:
        """取消订单并回补库存。

        只有 CREATED 状态可以取消。
        已支付订单请走退货流程，这样退款金额和库存回补都有据可查。

        Raises:
            NotFoundError: 订单不存在。
            ConflictError: 订单状态不允许取消。
        """
        now = datetime.now()

        try:
            order = self.order_repo.get_for_update(order_id)
            if order is None:
                raise NotFoundError(f"订单不存在: id={order_id}")

            if order.status == ORDER_STATUS_CANCELLED:
                raise ConflictError("订单已经取消，请勿重复操作")
            if order.status != ORDER_STATUS_CREATED:
                raise ConflictError(
                    f"订单当前状态为 {order.status}，不允许取消；"
                    "已支付订单请走退货流程"
                )

            # 回补每个商品的库存，并记录入库流水。
            for item in order.items:
                self._restock(
                    item=item,
                    quantity=item.quantity,
                    now=now,
                    operator=operator,
                    remark=f"订单取消回补 {order.order_no}",
                )

            order.status = ORDER_STATUS_CANCELLED
            order.cancelled_at = now
            order.cancel_reason = reason

            self.db.commit()
            cache.delete(CACHE_KEY_PRODUCT_STATS)
            cache.delete(CACHE_KEY_ORDER_STATS)
            return order

        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # 退货
    # ------------------------------------------------------------------
    def create_return(
        self,
        order_id: int,
        *,
        items: list[OrderReturnItemCreate],
        reason: str | None = None,
        operator: str | None = None,
    ) -> OrderReturn:
        """对已支付订单发起退货。

        支持部分退货：可以分多次退，累计退货数量不能超过购买数量。
        每次退货会:
            1. 生成退货单和退货明细；
            2. 回补商品库存和默认仓库库存；
            3. 写一条 IN 类型的库存流水；
            4. 累加订单退款金额，并把订单状态改为
               PARTIALLY_RETURNED（部分退货）或 RETURNED（全部退货）。

        Raises:
            ValidationError: 退货明细为空或数量不合法。
            NotFoundError: 订单或订单明细不存在。
            ConflictError: 订单状态不允许退货，或退货数量超过剩余可退数量。
        """
        if not items:
            raise ValidationError("退货单至少需要包含一项商品")

        # 同一明细多次提交时合并数量，避免重复校验/重复回补。
        merged_items: dict[int, int] = {}
        for item in items:
            if item.quantity <= 0:
                raise ValidationError("退货数量必须大于 0")
            merged_items[item.order_item_id] = (
                merged_items.get(item.order_item_id, 0) + item.quantity
            )

        now = datetime.now()
        return_no = f"RT{now:%Y%m%d%H%M%S}{uuid4().hex[:6].upper()}"

        try:
            order = self.order_repo.get_for_update(order_id)
            if order is None:
                raise NotFoundError(f"订单不存在: id={order_id}")

            if order.status not in (
                ORDER_STATUS_PAID,
                ORDER_STATUS_PARTIALLY_RETURNED,
            ):
                raise ConflictError(
                    f"订单当前状态为 {order.status}，只有已支付订单可以退货"
                )

            # 建立“订单明细 ID -> 明细对象”的索引。
            order_items = {item.id: item for item in order.items}

            order_return = OrderReturn(
                return_no=return_no,
                order_id=order.id,
                refund_amount=Decimal("0.00"),
                reason=reason,
                operator=operator,
                created_at=now,
            )
            self.db.add(order_return)
            self.db.flush()

            total_refund = Decimal("0.00")

            for order_item_id in sorted(merged_items):
                quantity = merged_items[order_item_id]
                item = order_items.get(order_item_id)
                if item is None:
                    raise NotFoundError(
                        f"订单明细不存在: id={order_item_id}"
                    )

                remaining = item.quantity - item.returned_quantity
                if quantity > remaining:
                    raise ConflictError(
                        f"商品 {item.sku} 最多还能退 {remaining} 件，"
                        f"本次提交 {quantity} 件"
                    )

                # 回补库存，并记录入库流水。
                self._restock(
                    item=item,
                    quantity=quantity,
                    now=now,
                    operator=operator,
                    remark=f"订单退货 {order.order_no}",
                )

                subtotal = Decimal(str(item.unit_price)) * quantity
                total_refund += subtotal

                # 记录本次退货明细，并累加订单明细的已退数量。
                item.returned_quantity += quantity
                order_return.items.append(
                    OrderReturnItem(
                        order_item_id=item.id,
                        product_id=item.product_id,
                        product_name=item.product_name,
                        sku=item.sku,
                        quantity=quantity,
                        unit_price=item.unit_price,
                        subtotal=subtotal,
                    )
                )

            order_return.refund_amount = total_refund
            order.refunded_amount = (
                Decimal(str(order.refunded_amount or 0)) + total_refund
            )

            # 全部明细都退完才算“已退货”，否则是“部分退货”。
            all_returned = all(
                item.returned_quantity >= item.quantity
                for item in order.items
            )
            order.status = (
                ORDER_STATUS_RETURNED
                if all_returned
                else ORDER_STATUS_PARTIALLY_RETURNED
            )

            self.db.commit()
            cache.delete(CACHE_KEY_PRODUCT_STATS)
            cache.delete(CACHE_KEY_ORDER_STATS)
            return order_return

        except Exception:
            self.db.rollback()
            raise

    def list_returns(self, order_id: int) -> list[OrderReturn]:
        """查询某个订单的全部退货记录。"""
        order = self.order_repo.get_by_id(order_id)
        if order is None:
            raise NotFoundError(f"订单不存在: id={order_id}")
        return self.order_return_repo.list_by_order(order_id)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get_order(self, order_id: int) -> Order:
        """查询订单详情。

        Raises:
            NotFoundError: 订单不存在。
        """
        order = self.order_repo.get_by_id(order_id)
        if order is None:
            raise NotFoundError(f"订单不存在: id={order_id}")
        return order

    def list_orders(
        self,
        *,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Order], int]:
        """分页查询订单。"""
        return self.order_repo.list_orders(
            status=status,
            keyword=keyword,
            page=page,
            size=size,
        )

    def get_stats(self) -> OrderStats:
        """统计已支付订单的销售额、订单数与累计利润。

        统计需要聚合订单明细与商品成本，开销较大且首页频繁刷新，
        因此与商品统计一样加一层短 TTL 缓存；支付、取消、退货后主动失效。
        """
        cached = cache.get_json(CACHE_KEY_ORDER_STATS)
        if cached is not None:
            try:
                return OrderStats(**cached)
            except (TypeError, ValueError):
                pass

        total_revenue, paid_order_count, total_profit = self.order_repo.stats()
        stats = OrderStats(
            paid_order_count=paid_order_count,
            total_revenue=total_revenue,
            total_profit=total_profit,
        )
        cache.set_json(CACHE_KEY_ORDER_STATS, stats.model_dump(mode="json"))
        return stats

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    def _restock(
        self,
        *,
        item: OrderItem,
        quantity: int,
        now: datetime,
        operator: str | None,
        remark: str,
    ) -> None:
        """把商品库存加回去，并写一条入库流水。

        调用前调用方已经用当前事务持有订单行锁，
        这里再对商品行加锁，保证并发下库存不会被算错。
        """
        product = self.product_repo.get_for_update(item.product_id)
        if product is None:
            raise NotFoundError(f"商品不存在: id={item.product_id}")

        # 先把默认仓库库存加回去（内部会按需初始化仓库库存）。
        self.warehouse_repo.apply_default_delta(product, quantity)

        before_quantity = product.quantity
        after_quantity = before_quantity + quantity
        product.quantity = after_quantity
        product.last_inbound_at = now

        self.db.add(
            InventoryLog(
                product_id=product.id,
                change_type="IN",
                change_quantity=quantity,
                before_quantity=before_quantity,
                after_quantity=after_quantity,
                operated_at=now,
                operator=operator,
                remark=remark,
            )
        )
