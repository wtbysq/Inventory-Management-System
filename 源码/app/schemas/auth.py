"""登录与用户管理 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """登录请求体。"""

    username: str = Field(
        min_length=1,
        max_length=64,
        description="登录名",
    )
    password: str = Field(
        min_length=1,
        max_length=128,
        description="登录密码",
    )


class UserOut(BaseModel):
    """用户信息响应，绝不返回 password_hash。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str | None
    role: str = Field(description="角色：admin / operator / viewer")
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class TokenOut(BaseModel):
    """登录成功响应。"""

    access_token: str = Field(description="JWT access token")
    token_type: str = Field(default="bearer", description="固定为 bearer")
    expires_in: int = Field(description="有效期，单位秒")
    user: UserOut


class UserCreate(BaseModel):
    """管理员创建用户。"""

    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[A-Za-z0-9_.-]+$",
        description="登录名，只允许字母、数字、下划线、点和短横线",
    )
    password: str = Field(
        min_length=6,
        max_length=128,
        description="初始密码，至少 6 位",
    )
    full_name: str | None = Field(default=None, max_length=64)
    role: str = Field(
        default="operator",
        description="角色：admin / operator / viewer",
    )


class UserUpdate(BaseModel):
    """管理员修改用户，字段为 None 表示不修改。"""

    full_name: str | None = Field(default=None, max_length=64)
    role: str | None = Field(
        default=None,
        description="角色：admin / operator / viewer",
    )
    is_active: bool | None = Field(default=None, description="是否启用")
    password: str | None = Field(
        default=None,
        min_length=6,
        max_length=128,
        description="重置密码，不传表示不修改",
    )


class ChangePasswordRequest(BaseModel):
    """用户自助修改密码。"""

    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)
