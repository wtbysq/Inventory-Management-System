"""订单 Schema：下单、支付、取消、退货。"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field


# ----------------------------------------------------------------------
# 下单
# ----------------------------------------------------------------------
class OrderItemCreate(BaseModel):
    """下单时的单个商品。"""

    product_id: int = Field(gt=0, description="商品ID")
    quantity: int = Field(gt=0, description="购买数量，必须大于 0")


class OrderCreate(BaseModel):
    """创建订单请求体。"""

    items: list[OrderItemCreate] = Field(
        min_length=1,
        description="订单商品列表，至少包含一个商品",
    )
    operator: str | None = Field(
        default=None,
        max_length=64,
        description="下单人",
    )
    remark: str | None = Field(
        default=None,
        max_length=255,
        description="订单备注",
    )


# ----------------------------------------------------------------------
# 支付 / 取消
# ----------------------------------------------------------------------
class OrderPayRequest(BaseModel):
    """订单支付请求体。"""

    payment_method: str = Field(
        default="BALANCE",
        max_length=32,
        description="支付方式：BALANCE / WECHAT / ALIPAY 等",
    )
    operator: str | None = Field(
        default=None,
        max_length=64,
        description="操作人",
    )


class OrderCancelRequest(BaseModel):
    """订单取消请求体。"""

    reason: str | None = Field(
        default=None,
        max_length=255,
        description="取消原因",
    )
    operator: str | None = Field(
        default=None,
        max_length=64,
        description="操作人",
    )


# ----------------------------------------------------------------------
# 退货
# ----------------------------------------------------------------------
class OrderReturnItemCreate(BaseModel):
    """按订单明细退货：order_item_id + 数量。"""

    order_item_id: int = Field(gt=0, description="订单明细ID")
    quantity: int = Field(gt=0, description="本次退货数量")


class OrderReturnCreate(BaseModel):
    """创建退货单请求体。"""

    items: list[OrderReturnItemCreate] = Field(
        min_length=1,
        description="退货明细，至少一项",
    )
    reason: str | None = Field(
        default=None,
        max_length=255,
        description="退货原因",
    )
    operator: str | None = Field(
        default=None,
        max_length=64,
        description="操作人",
    )


class OrderReturnItemOut(BaseModel):
    """退货明细响应。"""

    model_config = ConfigDict(from_attributes=True)

    order_item_id: int
    product_id: int
    product_name: str
    sku: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


class OrderReturnOut(BaseModel):
    """退货单响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    return_no: str
    order_id: int
    refund_amount: Decimal
    reason: str | None
    operator: str | None
    created_at: datetime
    items: list[OrderReturnItemOut]


# ----------------------------------------------------------------------
# 响应
# ----------------------------------------------------------------------
class OrderItemProductOut(BaseModel):
    """订单明细关联商品的成本信息（仅内部计算用，不输出到响应）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    cost: Decimal | None = None


class OrderItemOut(BaseModel):
    """订单明细响应结构。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    sku: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
    returned_quantity: int = Field(
        default=0,
        description="累计已退数量",
    )
    # 关联商品只用来读取成本价，序列化时排除。
    product: OrderItemProductOut | None = Field(default=None, exclude=True)

    @computed_field(description="单位成本价（取商品当前成本价）")
    @property
    def unit_cost(self) -> Decimal | None:
        """返回商品当前成本价，商品无成本价时返回 None。"""
        return self.product.cost if self.product else None


class OrderOut(BaseModel):
    """订单响应结构。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    total_amount: Decimal
    status: str
    operator: str | None
    remark: str | None
    paid_at: datetime | None = None
    payment_method: str | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    refunded_amount: Decimal = Decimal("0.00")
    created_at: datetime
    items: list[OrderItemOut]
    returns: list[OrderReturnOut] = Field(
        default_factory=list,
        description="退货记录",
    )

    @computed_field(
        description=(
            "订单利润：Σ(售价 - 成本价) × 未退货数量，"
            "成本价取商品当前成本；已取消订单为 0"
        )
    )
    @property
    def profit_amount(self) -> Decimal:
        """按商品当前成本价估算订单利润，退货部分不计入。"""
        if self.status == "CANCELLED":
            return Decimal("0.00")

        total = Decimal("0.00")
        for item in self.items:
            remaining = item.quantity - item.returned_quantity
            if remaining <= 0:
                continue
            cost = item.unit_cost or Decimal("0.00")
            total += (item.unit_price - cost) * remaining
        return total


class OrderStats(BaseModel):
    """订单经营统计，用于首页看板展示利润。"""

    paid_order_count: int = Field(description="已支付订单数（含退货）")
    total_revenue: Decimal = Field(description="销售总额，已扣除退款")
    total_profit: Decimal = Field(description="累计利润，按商品当前成本价计算")
