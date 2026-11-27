"""分类数据访问层。

Repository 只负责数据库查询，不包含业务判断。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category


class CategoryRepository:
    """分类表的数据访问对象。"""

    def __init__(self, db: Session) -> None:
        """保存数据库 Session。

        Args:
            db: SQLAlchemy Session，由 FastAPI 依赖注入传入。
        """
        self.db = db

    def list_all(self) -> list[Category]:
        """查询全部分类，按 ID 升序返回。"""
        stmt = select(Category).order_by(Category.id.asc())
        return list(self.db.scalars(stmt).all())

    def get_by_id(self, category_id: int) -> Category | None:
        """根据主键查询分类，不存在时返回 None。"""
        return self.db.get(Category, category_id)
