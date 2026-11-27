"""商品接口。"""

from fastapi import APIRouter, Depends, Path, Query

from app.core.security import require_login
from app.dependencies import get_product_service
from app.schemas.common import PageResponse, page_response
from app.schemas.product import ProductOut, ProductStats
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["商品管理"])


@router.get(
    "/stats",
    response_model=ProductStats,
    summary="库存统计",
    description=(
        "统计商品种类数、库存总数量、库存总价值和低库存商品数量。"
        "库存总价值 = sum(quantity * cost)。\n\n"
        "该接口默认开启缓存（`.env` 中 CACHE_ENABLED=true 时生效），"
        "任何库存写操作都会自动让缓存失效。"
    ),
    dependencies=[Depends(require_login)],
)
def get_inventory_stats(
    service: ProductService = Depends(get_product_service),
):
    """获取库存统计数据。"""
    return service.get_stats()


@router.get(
    "/low-stock",
    response_model=list[ProductOut],
    summary="低库存商品",
    description="查询当前库存小于低库存阈值的商品。",
    dependencies=[Depends(require_login)],
)
def list_low_stock_products(
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="最多返回多少条低库存商品",
    ),
    service: ProductService = Depends(get_product_service),
):
    """查询低库存商品列表。"""
    return service.get_low_stock_products(limit=limit)


@router.get(
    "",
    response_model=PageResponse[ProductOut],
    summary="分页查询商品",
    description=(
        "支持商品名称/SKU 模糊搜索、分类筛选、低库存筛选和分页。"
        "page 从 1 开始，size 最大 100。"
    ),
    dependencies=[Depends(require_login)],
)
def list_products(
    keyword: str | None = Query(
        default=None,
        description="商品名称或 SKU 模糊搜索关键字",
    ),
    category_id: int | None = Query(
        default=None,
        ge=1,
        description="分类 ID，不传表示全部分类",
    ),
    low_stock_only: bool = Query(
        default=False,
        description="是否只查询低库存商品",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="页码，从 1 开始",
    ),
    size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="每页数量，最大 100",
    ),
    service: ProductService = Depends(get_product_service),
):
    """分页查询商品。"""
    items, total = service.list_products(
        keyword=keyword,
        category_id=category_id,
        low_stock_only=low_stock_only,
        page=page,
        size=size,
    )

    # 由 FastAPI 根据 response_model 转换 ORM 对象。
    return page_response(items, total, page, size)


@router.get(
    "/{product_id}",
    response_model=ProductOut,
    summary="商品详情",
    description="根据商品 ID 查询商品详情，不存在时返回 404。",
    dependencies=[Depends(require_login)],
)
def get_product(
    product_id: int = Path(ge=1, description="商品 ID"),
    service: ProductService = Depends(get_product_service),
):
    """查询商品详情。"""
    return service.get_product(product_id)
