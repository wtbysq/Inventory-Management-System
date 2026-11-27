"""分类接口。"""

from fastapi import APIRouter, Depends

from app.core.security import require_login
from app.dependencies import get_category_service
from app.schemas.category import CategoryOut
from app.services.category_service import CategoryService

router = APIRouter(prefix="/categories", tags=["分类管理"])


@router.get(
    "",
    response_model=list[CategoryOut],
    summary="查询全部分类",
    dependencies=[Depends(require_login)],
)
def list_categories(
    service: CategoryService = Depends(get_category_service),
):
    """查询全部分类。"""
    return service.list_categories()
