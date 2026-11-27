"""用户与角色 ORM 模型。

权限控制采用最简单的 RBAC（基于角色的访问控制）：
    - 角色直接保存在 users.role 字段上；
    - 一个用户只有一个角色；
    - 具体权限由 `app/core/security.py` 中的 require_roles 判断。

角色:
    admin    管理员：全部功能，包含用户管理
    operator 操作员：业务数据的读写
    viewer   只读用户：只能查询
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import BIGINT_UNSIGNED_ID


class User(Base):
    """对应数据库表 users。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        primary_key=True,
        autoincrement=True,
        comment="用户ID",
    )
    username: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="登录名，全局唯一",
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="PBKDF2 密码哈希，绝不保存明文",
    )
    full_name: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="显示名称",
    )
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="operator",
        index=True,
        comment="角色：admin / operator / viewer",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否启用，False 表示禁止登录",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="最近登录时间",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<User id={self.id} username={self.username!r} "
            f"role={self.role!r}>"
        )
