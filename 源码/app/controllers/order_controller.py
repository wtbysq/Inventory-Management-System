"""订单接口：下单、支付、取消、退货、查询。"""

from fastapi import APIRouter, Depends, Path, Query

from app.core.rate_limit import rate_limit
from app.core.security import (
    CurrentUser,
    get_current_user,
    require_login,
    require_operator,
)
from app.dependencies import get_order_service
from app.models.user import User
from app.schemas.common import PageResponse, page_response
from app.schemas.order import (
    OrderCancelRequest,
    OrderCreate,
    OrderOut,
    OrderPayRequest,
    OrderReturnCreate,
    OrderReturnOut,
    OrderStats,
)
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["订单管理"])


@router.post(
    "",
    response_model=OrderOut,
    status_code=201,
    summary="创建订单并扣减库存",
    description=(
        "创建订单时会在同一个事务中扣减所有商品库存、"
        "生成订单明细和库存出库流水。"
        "任意商品库存不足时整个订单回滚。\n\n"
        "限流：每个 IP 每分钟最多 60 单。"
    ),
    dependencies=[
        Depends(require_operator),
        Depends(rate_limit(scope="order_create", limit=60, window_seconds=60)),
    ],
)
def create_order(
    payload: OrderCreate,
    current_user: CurrentUser,
    service: OrderService = Depends(get_order_service),
):
    """创建订单。"""
    return service.create_order(
        items=payload.items,
        operator=payload.operator or current_user.username,
        remark=payload.remark,
    )


@router.get(
    "",
    response_model=PageResponse[OrderOut],
    summary="分页查询订单",
    description=(
        "支持按订单状态筛选和订单号模糊搜索。\n\n"
        "状态：CREATED / PAID / CANCELLED / PARTIALLY_RETURNED / RETURNED"
    ),
    dependencies=[Depends(require_login)],
)
def list_orders(
    status: str | None = Query(
        default=None,
        description="订单状态",
    ),
    keyword: str | None = Query(
        default=None,
        description="订单号模糊搜索",
    ),
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="每页数量",
    ),
    service: OrderService = Depends(get_order_service),
):
    """分页查询订单。"""
    items, total = service.list_orders(
        status=status,
        keyword=keyword,
        page=page,
        size=size,
    )
    return page_response(items, total, page, size)


@router.get(
    "/stats",
    response_model=OrderStats,
    summary="订单经营统计",
    description=(
        "统计已支付订单（含部分退货、已退货）的销售总额、订单数和累计利润。\n\n"
        "利润按 (售价 - 商品当前成本价) × 未退货数量 汇总。"
    ),
    dependencies=[Depends(require_login)],
)
def order_stats(service: OrderService = Depends(get_order_service)):
    """返回订单经营统计，用于首页看板。"""
    return service.get_stats()


@router.get(
    "/{order_id}",
    response_model=OrderOut,
    summary="订单详情",
    description="根据订单 ID 查询订单、明细和退货记录。",
    dependencies=[Depends(require_login)],
)
def get_order(
    order_id: int = Path(ge=1, description="订单 ID"),
    service: OrderService = Depends(get_order_service),
):
    """查询订单详情。"""
    return service.get_order(order_id)


@router.post(
    "/{order_id}/pay",
    response_model=OrderOut,
    summary="支付订单",
    description=(
        "把订单状态从 CREATED 改为 PAID，记录支付时间与支付方式。\n\n"
        "重复支付返回 409。演示项目不接入真实支付渠道。"
    ),
    dependencies=[Depends(require_operator)],
)
def pay_order(
    payload: OrderPayRequest,
    order_id: int = Path(ge=1, description="订单 ID"),
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
):
    """支付订单。"""
    return service.pay_order(
        order_id,
        payment_method=payload.payment_method,
        operator=payload.operator or current_user.username,
    )


@router.post(
    "/{order_id}/cancel",
    response_model=OrderOut,
    summary="取消订单",
    description=(
        "只有 CREATED 状态的订单可以取消。\n\n"
        "取消时会把订单内所有商品库存加回去，并写入 IN 类型的库存流水。"
    ),
    dependencies=[Depends(require_operator)],
)
def cancel_order(
    payload: OrderCancelRequest,
    order_id: int = Path(ge=1, description="订单 ID"),
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
):
    """取消订单并回补库存。"""
    return service.cancel_order(
        order_id,
        reason=payload.reason,
        operator=payload.operator or current_user.username,
    )


@router.post(
    "/{order_id}/returns",
    response_model=OrderReturnOut,
    status_code=201,
    summary="订单退货",
    description=(
        "对已支付订单发起退货，支持部分退货、多次退货。\n\n"
        "退货会生成退货单、回补库存并写入 IN 流水；"
        "累计退货数量不能超过购买数量。"
    ),
    dependencies=[Depends(require_operator)],
)
def create_order_return(
    payload: OrderReturnCreate,
    order_id: int = Path(ge=1, description="订单 ID"),
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
):
    """创建退货单。"""
    return service.create_return(
        order_id,
        items=payload.items,
        reason=payload.reason,
        operator=payload.operator or current_user.username,
    )


@router.get(
    "/{order_id}/returns",
    response_model=list[OrderReturnOut],
    summary="订单退货记录",
    dependencies=[Depends(require_login)],
)
def list_order_returns(
    order_id: int = Path(ge=1, description="订单 ID"),
    service: OrderService = Depends(get_order_service),
):
    """查询某个订单的全部退货单。"""
    return service.list_returns(order_id)
