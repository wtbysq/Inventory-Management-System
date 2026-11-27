"""库存出入库接口。"""

from fastapi import APIRouter, Depends, Query

from app.core.rate_limit import rate_limit
from app.core.security import require_login, require_operator
from app.dependencies import get_inventory_service
from app.schemas.common import PageResponse, page_response
from app.schemas.inventory import InventoryChangeRequest, InventoryLogOut
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/inventory", tags=["库存管理"])


@router.post(
    "/inbound",
    response_model=InventoryLogOut,
    status_code=201,
    summary="商品入库",
    description=(
        "增加商品库存（默认仓库同步增加），生成一条 IN 类型的库存流水。"
    ),
    dependencies=[
        Depends(require_operator),
        Depends(rate_limit(scope="inventory_write", limit=120)),
    ],
)
def inbound(
    payload: InventoryChangeRequest,
    service: InventoryService = Depends(get_inventory_service),
):
    """商品入库。"""
    return service.inbound(
        product_id=payload.product_id,
        quantity=payload.quantity,
        operator=payload.operator,
        remark=payload.remark,
    )


@router.post(
    "/outbound",
    response_model=InventoryLogOut,
    status_code=201,
    summary="商品出库",
    description=(
        "扣减商品库存（默认仓库同步扣减），生成一条 OUT 类型的库存流水。"
        "库存不足时返回 409，库存和流水都不会变化。"
    ),
    dependencies=[
        Depends(require_operator),
        Depends(rate_limit(scope="inventory_write", limit=120)),
    ],
)
def outbound(
    payload: InventoryChangeRequest,
    service: InventoryService = Depends(get_inventory_service),
):
    """商品出库。"""
    return service.outbound(
        product_id=payload.product_id,
        quantity=payload.quantity,
        operator=payload.operator,
        remark=payload.remark,
    )


@router.get(
    "/logs",
    response_model=PageResponse[InventoryLogOut],
    summary="库存流水",
    description=(
        "分页查询库存流水，可按商品和类型过滤。\n\n"
        "类型：IN 入库 / OUT 出库 / ADJUST 盘点调整。"
    ),
    dependencies=[Depends(require_login)],
)
def list_inventory_logs(
    product_id: int | None = Query(
        default=None,
        ge=1,
        description="商品 ID，不传表示查询全部流水",
    ),
    change_type: str | None = Query(
        default=None,
        description="流水类型：IN / OUT / ADJUST",
    ),
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="每页数量",
    ),
    service: InventoryService = Depends(get_inventory_service),
):
    """分页查询库存流水。"""
    items, total = service.list_logs(
        product_id=product_id,
        change_type=change_type,
        page=page,
        size=size,
    )
    return page_response(items, total, page, size)
