"""用户数据访问层。"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """users 表的数据访问对象。"""

    def __init__(self, db: Session) -> None:
        """保存数据库 Session。"""
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        """按主键查询用户。"""
        return self.db.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        """按登录名查询用户，用于登录和唯一性校验。"""
        stmt = select(User).where(User.username == username)
        return self.db.scalar(stmt)

    def add(self, user: User) -> User:
        """新增用户并 flush 获取自增 ID，事务由 Service 控制。"""
        self.db.add(user)
        self.db.flush()
        return user

    def count_all(self) -> int:
        """统计用户总数，启动时判断是否需要初始化管理员。"""
        return int(self.db.scalar(select(func.count(User.id))) or 0)

    def count_active_admins(self) -> int:
        """统计启用状态的管理员数量。

        用于防止把最后一个管理员降级或禁用，导致系统没人能管理用户。
        """
        stmt = select(func.count(User.id)).where(
            User.role == "admin",
            User.is_active.is_(True),
        )
        return int(self.db.scalar(stmt) or 0)

    def list_users(
        self,
        *,
        keyword: str | None = None,
        role: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[User], int]:
        """分页查询用户，支持用户名/姓名模糊搜索和角色筛选。"""
        conditions = []

        if keyword:
            like_value = f"%{keyword}%"
            conditions.append(
                or_(
                    User.username.like(like_value),
                    User.full_name.like(like_value),
                )
            )
        if role:
            conditions.append(User.role == role)

        base_stmt = select(User)
        if conditions:
            base_stmt = base_stmt.where(*conditions)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = int(self.db.scalar(count_stmt) or 0)

        items_stmt = (
            base_stmt.order_by(User.id.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(self.db.scalars(items_stmt).all()), total
