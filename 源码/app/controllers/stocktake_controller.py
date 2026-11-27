"""库存盘点接口。"""

from fastapi import APIRouter, Depends, Path, Query

from app.core.security import (
    CurrentUser,
    get_current_user,
    require_login,
    require_operator,
)
from app.dependencies import get_stocktake_service
from app.models.user import User
from app.schemas.common import PageResponse, page_response
from app.schemas.stocktake import (
    StocktakeCountRequest,
    StocktakeCreate,
    StocktakeOut,
)
from app.services.stocktake_service import StocktakeService

router = APIRouter(prefix="/stocktakes", tags=["库存盘点"])


@router.post(
    "",
    response_model=StocktakeOut,
    status_code=201,
    summary="创建盘点单",
    description=(
        "按分类或指定商品创建盘点单，创建时会把当前库存抄成账面数量。\n\n"
        "不传 category_id 和 product_ids 时盘点全部商品。"
    ),
    dependencies=[Depends(require_operator)],
)
def create_stocktake(
    payload: StocktakeCreate,
    current_user: CurrentUser,
    service: StocktakeService = Depends(get_stocktake_service),
):
    """创建盘点单。"""
    return service.create_stocktake(
        category_id=payload.category_id,
        product_ids=payload.product_ids,
        operator=payload.operator or current_user.username,
        remark=payload.remark,
    )


@router.get(
    "",
    response_model=PageResponse[StocktakeOut],
    summary="分页查询盘点单",
    dependencies=[Depends(require_login)],
)
def list_stocktakes(
    status: str | None = Query(
        default=None,
        description="COUNTING / CONFIRMED / CANCELLED",
    ),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    service: StocktakeService = Depends(get_stocktake_service),
):
    """分页查询盘点单。"""
    items, total = service.list_stocktakes(
        status=status,
        page=page,
        size=size,
    )
    return page_response(items, total, page, size)


@router.get(
    "/{stocktake_id}",
    response_model=StocktakeOut,
    summary="盘点单详情",
    dependencies=[Depends(require_login)],
)
def get_stocktake(
    stocktake_id: int = Path(ge=1, description="盘点单 ID"),
    service: StocktakeService = Depends(get_stocktake_service),
):
    """查询盘点单及明细。"""
    return service.get_stocktake(stocktake_id)


@router.post(
    "/{stocktake_id}/count",
    response_model=StocktakeOut,
    summary="录入实盘数量",
    description="批量录入实盘数量，可多次调用，最后一次录入为准。",
    dependencies=[Depends(require_operator)],
)
def count_stocktake(
    payload: StocktakeCountRequest,
    stocktake_id: int = Path(ge=1, description="盘点单 ID"),
    service: StocktakeService = Depends(get_stocktake_service),
):
    """批量录入实盘数量。"""
    return service.count_items(
        stocktake_id,
        items=[item.model_dump() for item in payload.items],
    )


@router.post(
    "/{stocktake_id}/confirm",
    response_model=StocktakeOut,
    summary="确认盘点",
    description=(
        "按实盘数量修正库存，生成 ADJUST 类型的库存流水。\n\n"
        "未录入实盘数量的商品会被跳过。"
    ),
    dependencies=[Depends(require_operator)],
)
def confirm_stocktake(
    stocktake_id: int = Path(ge=1, description="盘点单 ID"),
    current_user: User = Depends(get_current_user),
    service: StocktakeService = Depends(get_stocktake_service),
):
    """确认盘点并调整库存。"""
    return service.confirm_stocktake(
        stocktake_id,
        operator=current_user.username,
    )


@router.post(
    "/{stocktake_id}/cancel",
    response_model=StocktakeOut,
    summary="取消盘点",
    description="取消盘点单，不会修改库存。",
    dependencies=[Depends(require_operator)],
)
def cancel_stocktake(
    stocktake_id: int = Path(ge=1, description="盘点单 ID"),
    service: StocktakeService = Depends(get_stocktake_service),
):
    """取消盘点单。"""
    return service.cancel_stocktake(stocktake_id)
