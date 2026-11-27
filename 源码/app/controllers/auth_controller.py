"""登录认证接口。"""

from fastapi import APIRouter, Depends

from app.core.rate_limit import rate_limit
from app.core.security import CurrentUser
from app.dependencies import get_auth_service
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    TokenOut,
    UserOut,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["登录认证"])


@router.post(
    "/login",
    response_model=TokenOut,
    summary="登录获取 token",
    description=(
        "使用用户名和密码登录。成功后返回 JWT，"
        "后续请求需要在请求头中携带：`Authorization: Bearer <token>`。\n\n"
        "为防止暴力破解，登录接口做了限流：每个 IP 每分钟最多 10 次。"
    ),
    dependencies=[
        Depends(rate_limit(scope="login", limit=10, window_seconds=60))
    ],
)
def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
):
    """登录并签发 access token。"""
    user, token, expires_in = service.login(
        username=payload.username,
        password=payload.password,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": user,
    }


@router.get(
    "/me",
    response_model=UserOut,
    summary="当前登录用户",
    description="根据请求头中的 token 返回当前用户信息。",
)
def get_me(current_user: CurrentUser):
    """返回当前登录用户。"""
    return current_user


@router.post(
    "/change-password",
    summary="修改自己的密码",
    description="校验原密码后设置新密码。",
)
def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    service: AuthService = Depends(get_auth_service),
):
    """修改当前登录用户的密码。"""
    service.change_password(
        user=current_user,
        old_password=payload.old_password,
        new_password=payload.new_password,
    )
    return {"message": "密码修改成功，请使用新密码重新登录"}
