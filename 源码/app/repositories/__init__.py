"""数据访问层。

Repository 负责 SQL 查询和持久化，不包含业务规则。
"""

from app.repositories.category_repo import CategoryRepository
from app.repositories.inventory_log_repo import InventoryLogRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.order_return_repo import OrderReturnRepository
from app.repositories.product_repo import ProductRepository
from app.repositories.stocktake_repo import StocktakeRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.transfer_repo import TransferRepository
from app.repositories.user_repo import UserRepository
from app.repositories.warehouse_repo import WarehouseRepository

__all__ = [
    "CategoryRepository",
    "InventoryLogRepository",
    "OrderRepository",
    "OrderReturnRepository",
    "ProductRepository",
    "StocktakeRepository",
    "TaskRepository",
    "TransferRepository",
    "UserRepository",
    "WarehouseRepository",
]
