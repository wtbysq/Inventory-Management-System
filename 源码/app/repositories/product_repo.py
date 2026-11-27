"""商品数据访问层。

所有商品相关的 SQL 都集中在这里，包括：
- 分页查询
- 关键字模糊搜索
- 低库存筛选
- 库存价值统计
- 行锁查询
"""

from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.product import Product


def _to_decimal(value: object) -> Decimal:
    """把数据库返回的数值安全转换为 Decimal。

    MySQL 的 SUM(DECIMAL) 通常返回 Decimal，
    SQLite 测试环境可能返回 int/float，这里统一处理。
    """
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


class ProductRepository:
    """商品表的数据访问对象。"""

    def __init__(self, db: Session) -> None:
        """保存数据库 Session。

        Args:
            db: SQLAlchemy Session，由 FastAPI 依赖注入传入。
        """
        self.db = db

    def get_by_id(self, product_id: int) -> Product | None:
        """根据商品 ID 查询商品，不存在时返回 None。"""
        return self.db.get(Product, product_id)

    def get_by_sku(self, sku: str) -> Product | None:
        """根据 SKU 查询商品，主要用于唯一性校验。"""
        stmt = select(Product).where(Product.sku == sku)
        return self.db.scalar(stmt)

    def get_for_update(self, product_id: int) -> Product | None:
        """在事务中锁定商品行。

        MySQL InnoDB 下会生成 SELECT ... FOR UPDATE，
        用于防止并发出库导致超卖。

        注意:
            必须在事务中调用，否则行锁会立即释放。
        """
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .with_for_update()
        )
        return self.db.scalar(stmt)

    def search(
        self,
        *,
        keyword: str | None = None,
        category_id: int | None = None,
        low_stock_only: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Product], int]:
        """分页查询商品。

        Args:
            keyword: 商品名称或 SKU 的模糊搜索关键字。
            category_id: 分类 ID，传 None 表示不筛选分类。
            low_stock_only: 是否只查询低库存商品。
            page: 页码，从 1 开始。
            size: 每页数量。

        Returns:
            (当前页商品列表, 总记录数)
        """
        conditions = []

        # 关键字同时匹配商品名称和 SKU。
        if keyword:
            like_value = f"%{keyword}%"
            conditions.append(
                or_(
                    Product.product_name.like(like_value),
                    Product.sku.like(like_value),
                )
            )

        # 按分类筛选。
        if category_id is not None:
            conditions.append(Product.category_id == category_id)

        # 低库存：当前库存小于低库存阈值。
        if low_stock_only:
            conditions.append(
                Product.quantity < Product.low_stock_threshold
            )

        base_stmt = select(Product)
        if conditions:
            base_stmt = base_stmt.where(*conditions)

        # 先基于相同条件统计总数，再查询当前页数据。
        count_stmt = select(func.count()).select_from(
            base_stmt.subquery()
        )
        total = int(self.db.scalar(count_stmt) or 0)

        items_stmt = (
            base_stmt
            .order_by(Product.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = list(self.db.scalars(items_stmt).all())

        return items, total

    def list_for_stocktake(
        self,
        *,
        category_id: int | None = None,
        product_ids: list[int] | None = None,
        limit: int = 5000,
    ) -> list[Product]:
        """查询需要盘点的商品。

        盘点是一次性快照，因此这里直接返回列表而不是分页，
        但用 limit 防止误操作把几十万商品全部加载进内存。
        """
        stmt = select(Product).order_by(Product.id.asc())

        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
        if product_ids:
            stmt = stmt.where(Product.id.in_(product_ids))

        return list(self.db.scalars(stmt.limit(limit)).all())

    def count_all(self) -> int:
        """统计商品种类数。"""
        stmt = select(func.count(Product.id))
        return int(self.db.scalar(stmt) or 0)

    def total_quantity(self) -> int:
        """统计所有商品的库存总数量。"""
        stmt = select(func.coalesce(func.sum(Product.quantity), 0))
        return int(self.db.scalar(stmt) or 0)

    def total_inventory_value(self) -> Decimal:
        """统计库存总价值：sum(quantity * cost)。

        cost 为 NULL 的商品按 0 计算，避免整行被 SUM 忽略后产生误解。
        """
        stmt = select(
            func.coalesce(
                func.sum(
                    Product.quantity * func.coalesce(Product.cost, 0)
                ),
                0,
            )
        )
        return _to_decimal(self.db.scalar(stmt))

    def count_low_stock(self) -> int:
        """统计低库存商品数量。"""
        stmt = select(func.count(Product.id)).where(
            Product.quantity < Product.low_stock_threshold
        )
        return int(self.db.scalar(stmt) or 0)
