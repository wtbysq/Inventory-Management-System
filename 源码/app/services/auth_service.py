"""认证与用户管理业务逻辑。

包含:
    - 登录：校验密码 + 签发 JWT
    - 用户增删改查（仅管理员可用，权限在 Controller 层校验）
    - 自助修改密码
    - 启动时初始化默认管理员
"""

import logging
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.core.security import (
    ROLE_ADMIN,
    ROLE_LABELS,
    ROLE_OPERATOR,
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)


class AuthService:
    """登录与用户管理。"""

    def __init__(self, db: Session) -> None:
        """初始化认证 Service。"""
        self.db = db
        self.user_repo = UserRepository(db)

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------
    def login(
        self,
        *,
        username: str,
        password: str,
    ) -> tuple[User, str, int]:
        """校验账号密码并签发 token。

        Returns:
            (用户, access_token, 有效期秒数)

        Raises:
            UnauthorizedError: 用户名不存在或密码错误（不区分，防止账号枚举）。
            ForbiddenError: 账号被禁用。
        """
        user = self.user_repo.get_by_username(username.strip())

        if user is None or not verify_password(password, user.password_hash):
            raise UnauthorizedError("用户名或密码错误")

        if not user.is_active:
            raise ForbiddenError("账号已被禁用，请联系管理员")

        user.last_login_at = datetime.now()
        token, expires_in = create_access_token(
            user_id=user.id,
            username=user.username,
            role=user.role,
        )
        self.db.commit()
        return user, token, expires_in

    # ------------------------------------------------------------------
    # 用户查询
    # ------------------------------------------------------------------
    def get_user(self, user_id: int) -> User:
        """查询用户详情。"""
        user = self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"用户不存在: id={user_id}")
        return user

    def list_users(
        self,
        *,
        keyword: str | None = None,
        role: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[User], int]:
        """分页查询用户。"""
        if role:
            self._validate_role(role)
        return self.user_repo.list_users(
            keyword=keyword,
            role=role,
            page=page,
            size=size,
        )

    # ------------------------------------------------------------------
    # 用户管理
    # ------------------------------------------------------------------
    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: str = ROLE_OPERATOR,
        full_name: str | None = None,
    ) -> User:
        """创建用户。

        Raises:
            ValidationError: 角色不合法。
            ConflictError: 登录名已存在。
        """
        self._validate_role(role)
        username = username.strip()

        if self.user_repo.get_by_username(username) is not None:
            raise ConflictError(f"登录名已存在: {username}")

        user = User(
            username=username,
            password_hash=hash_password(password),
            full_name=full_name,
            role=role,
            is_active=True,
        )

        try:
            self.user_repo.add(user)
            self.db.commit()
        except IntegrityError as exc:
            # 并发创建同名用户时由数据库唯一索引兜底。
            self.db.rollback()
            raise ConflictError(f"登录名已存在: {username}") from exc

        return user

    def update_user(
        self,
        user_id: int,
        *,
        changes: dict,
    ) -> User:
        """修改用户信息（部分更新）。

        Args:
            changes: 只包含需要修改的字段。
        """
        user = self.get_user(user_id)

        if "role" in changes and changes["role"] is not None:
            new_role = str(changes["role"])
            self._validate_role(new_role)

            # 不能把最后一个启用管理员降级，否则没人能管理系统。
            if (
                user.role == ROLE_ADMIN
                and new_role != ROLE_ADMIN
                and self.user_repo.count_active_admins() <= 1
            ):
                raise ConflictError("系统至少需要保留一个启用的管理员")

            user.role = new_role

        if "full_name" in changes:
            user.full_name = changes["full_name"]

        if "is_active" in changes and changes["is_active"] is not None:
            is_active = bool(changes["is_active"])

            if (
                user.role == ROLE_ADMIN
                and not is_active
                and self.user_repo.count_active_admins() <= 1
            ):
                raise ConflictError("系统至少需要保留一个启用的管理员")

            user.is_active = is_active

        if changes.get("password"):
            user.password_hash = hash_password(str(changes["password"]))

        self.db.commit()
        return user

    def change_password(
        self,
        *,
        user: User,
        old_password: str,
        new_password: str,
    ) -> None:
        """用户自助修改密码。"""
        if not verify_password(old_password, user.password_hash):
            raise ValidationError("原密码不正确")

        if old_password == new_password:
            raise ValidationError("新密码不能与原密码相同")

        user.password_hash = hash_password(new_password)
        self.db.commit()

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_role(role: str) -> None:
        """校验角色是否合法。"""
        if role not in ROLE_LABELS:
            allowed = " / ".join(ROLE_LABELS)
            raise ValidationError(f"角色不合法: {role}，可选：{allowed}")


def bootstrap_default_admin() -> None:
    """服务启动时初始化默认管理员。

    只在用户表为空时创建，不会覆盖已有账号。
    用 try/except 包住的原因：
        数据库可能还没执行迁移（users 表不存在），
        此时不应该阻止整个应用启动，只打印一条警告。
    """
    # 延迟导入，避免模块级循环依赖。
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        repo = UserRepository(db)
        if repo.count_all() > 0:
            return

        admin = User(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
            full_name="系统管理员",
            role=ROLE_ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        logger.warning(
            "已创建默认管理员 %s，初始密码 %s，请登录后立即修改！",
            settings.admin_username,
            settings.admin_password,
        )
    except Exception as exc:  # noqa: BLE001 - 启动阶段不应因数据库未迁移而崩溃
        db.rollback()
        logger.warning(
            "初始化默认管理员失败，请确认已执行数据库迁移：%s",
            exc,
        )
    finally:
        db.close()
