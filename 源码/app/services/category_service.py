"""分类业务逻辑层。"""

from sqlalchemy.orm import Session

from app.models.category import Category
from app.repositories.category_repo import CategoryRepository


class CategoryService:
    """分类相关业务。"""

    def __init__(self, db: Session) -> None:
        """初始化分类 Service。"""
        self.db = db
        self.category_repo = CategoryRepository(db)

    def list_categories(self) -> list[Category]:
        """查询全部分类。"""
        return self.category_repo.list_all()
