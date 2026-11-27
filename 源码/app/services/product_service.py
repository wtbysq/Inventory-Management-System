"""商品业务逻辑层。"""

from sqlalchemy.orm import Session

from app.core.cache import CACHE_KEY_PRODUCT_STATS, cache
from app.core.exceptions import NotFoundError
from app.models.product import Product
from app.repositories.product_repo import ProductRepository
from app.schemas.product import ProductStats


class ProductService:
    """商品查询与统计业务。"""

    def __init__(self, db: Session) -> None:
        """初始化商品 Service。"""
        self.db = db
        self.product_repo = ProductRepository(db)

    def list_products(
        self,
        *,
        keyword: str | None = None,
        category_id: int | None = None,
        low_stock_only: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Product], int]:
        """分页查询商品。

        参数含义与 Repository.search 一致。
        """
        return self.product_repo.search(
            keyword=keyword,
            category_id=category_id,
            low_stock_only=low_stock_only,
            page=page,
            size=size,
        )

    def get_product(self, product_id: int) -> Product:
        """查询商品详情。

        Raises:
            NotFoundError: 商品不存在时抛出。
        """
        product = self.product_repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError(f"商品不存在: id={product_id}")
        return product

    def get_low_stock_products(self, limit: int = 20) -> list[Product]:
        """查询低库存商品，按 ID 倒序返回。"""
        items, _ = self.product_repo.search(
            low_stock_only=True,
            page=1,
            size=limit,
        )
        return items

    def get_stats(self) -> ProductStats:
        """统计商品数量、库存总量、库存总价值和低库存数量。

        这是首页看板接口，访问频率高、统计开销大（需要全表扫描），
        因此加一层缓存：
            - 命中缓存直接返回；
            - 未命中则查库并写入缓存（默认 30 秒）；
            - 任何库存写操作都会删除该缓存，保证数据不会长时间不一致。
        """
        cached = cache.get_json(CACHE_KEY_PRODUCT_STATS)
        if cached is not None:
            try:
                return ProductStats(**cached)
            except (TypeError, ValueError):
                # 缓存内容格式异常时忽略缓存，回退到数据库查询。
                pass

        stats = ProductStats(
            total_products=self.product_repo.count_all(),
            total_quantity=self.product_repo.total_quantity(),
            total_inventory_value=self.product_repo.total_inventory_value(),
            low_stock_count=self.product_repo.count_low_stock(),
        )

        # mode="json" 把 Decimal 转成字符串，避免 JSON 序列化精度问题。
        cache.set_json(CACHE_KEY_PRODUCT_STATS, stats.model_dump(mode="json"))
        return stats
