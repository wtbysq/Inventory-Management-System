"""用户管理接口（仅管理员）。"""

from fastapi import APIRouter, Depends, Path, Query

from app.core.exceptions import ValidationError
from app.core.security import require_admin
from app.dependencies import get_auth_service
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.schemas.common import PageResponse, page_response
from app.services.auth_service import AuthService

# 整个路由组统一要求管理员权限，避免每个接口重复声明。
router = APIRouter(
    prefix="/users",
    tags=["用户管理"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "",
    response_model=PageResponse[UserOut],
    summary="分页查询用户",
    description="仅管理员可访问。",
)
def list_users(
    keyword: str | None = Query(
        default=None,
        description="用户名或姓名模糊搜索",
    ),
    role: str | None = Query(
        default=None,
        description="角色筛选：admin / operator / viewer",
    ),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    service: AuthService = Depends(get_auth_service),
):
    """分页查询用户。"""
    items, total = service.list_users(
        keyword=keyword,
        role=role,
        page=page,
        size=size,
    )
    return page_response(items, total, page, size)


@router.post(
    "",
    response_model=UserOut,
    status_code=201,
    summary="创建用户",
    description="仅管理员可创建用户，密码至少 6 位。",
)
def create_user(
    payload: UserCreate,
    service: AuthService = Depends(get_auth_service),
):
    """创建用户。"""
    return service.create_user(
        username=payload.username,
        password=payload.password,
        role=payload.role,
        full_name=payload.full_name,
    )


@router.patch(
    "/{user_id}",
    response_model=UserOut,
    summary="修改用户",
    description=(
        "可修改姓名、角色、启用状态，也可以重置密码。\n\n"
        "系统会保证至少保留一个启用的管理员。"
    ),
)
def update_user(
    payload: UserUpdate,
    user_id: int = Path(ge=1, description="用户 ID"),
    service: AuthService = Depends(get_auth_service),
):
    """局部更新用户信息。"""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationError("没有需要修改的字段")
    return service.update_user(user_id, changes=changes)
