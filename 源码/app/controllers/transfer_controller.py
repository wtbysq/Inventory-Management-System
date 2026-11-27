"""仓库与库存调拨接口。"""

from fastapi import APIRouter, Depends, Path, Query

from app.core.security import CurrentUser, require_login, require_operator
from app.dependencies import get_transfer_service, get_warehouse_service
from app.schemas.common import PageResponse, page_response
from app.schemas.transfer import (
    TransferCreate,
    TransferOut,
    WarehouseCreate,
    WarehouseOut,
)
from app.services.transfer_service import TransferService, WarehouseService

router = APIRouter(prefix="/transfers", tags=["库存调拨"])


@router.post(
    "",
    response_model=TransferOut,
    status_code=201,
    summary="创建调拨单",
    description=(
        "把商品从一个仓库调到另一个仓库。\n\n"
        "调拨只改变仓库库存，不改变商品总库存，"
        "因此不会写入库存流水，调拨单本身即审计凭证。"
    ),
    dependencies=[Depends(require_operator)],
)
def create_transfer(
    payload: TransferCreate,
    current_user: CurrentUser,
    service: TransferService = Depends(get_transfer_service),
):
    """创建并完成调拨。"""
    return service.create_transfer(
        from_warehouse_id=payload.from_warehouse_id,
        to_warehouse_id=payload.to_warehouse_id,
        items=payload.items,
        operator=payload.operator or current_user.username,
        remark=payload.remark,
    )


@router.get(
    "",
    response_model=PageResponse[TransferOut],
    summary="分页查询调拨单",
    description="可按仓库筛选（调出或调入仓库匹配即可）。",
    dependencies=[Depends(require_login)],
)
def list_transfers(
    warehouse_id: int | None = Query(
        default=None,
        ge=1,
        description="仓库 ID，不传表示全部",
    ),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    service: TransferService = Depends(get_transfer_service),
):
    """分页查询调拨单。"""
    items, total = service.list_transfers(
        warehouse_id=warehouse_id,
        page=page,
        size=size,
    )
    return page_response(items, total, page, size)


@router.get(
    "/{transfer_id}",
    response_model=TransferOut,
    summary="调拨单详情",
    dependencies=[Depends(require_login)],
)
def get_transfer(
    transfer_id: int = Path(ge=1, description="调拨单 ID"),
    service: TransferService = Depends(get_transfer_service),
):
    """查询调拨单详情。"""
    return service.get_transfer(transfer_id)


# ----------------------------------------------------------------------
# 仓库
# ----------------------------------------------------------------------
warehouse_router = APIRouter(prefix="/warehouses", tags=["仓库管理"])


@warehouse_router.get(
    "",
    response_model=list[WarehouseOut],
    summary="仓库列表",
    description="首次访问会自动创建默认仓库 MAIN。",
    dependencies=[Depends(require_login)],
)
def list_warehouses(
    service: WarehouseService = Depends(get_warehouse_service),
):
    """查询全部仓库。"""
    return service.list_warehouses()


@warehouse_router.post(
    "",
    response_model=WarehouseOut,
    status_code=201,
    summary="创建仓库",
    description="操作员或管理员可以创建仓库，编码会自动转为大写。",
    dependencies=[Depends(require_operator)],
)
def create_warehouse(
    payload: WarehouseCreate,
    service: WarehouseService = Depends(get_warehouse_service),
):
    """创建仓库。"""
    return service.create_warehouse(
        code=payload.code,
        name=payload.name,
        address=payload.address,
    )
