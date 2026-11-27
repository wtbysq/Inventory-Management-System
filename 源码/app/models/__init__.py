"""SQLAlchemy ORM 模型。

在这里统一导入所有模型，确保 Base.metadata 能注册全部表，
测试时 Base.metadata.create_all() 才能创建完整表结构，
Alembic 自动生成迁移也依赖这里。
"""

from app.models.category import Category
from app.models.inventory_log import InventoryLog
from app.models.order import (
    ORDER_STATUS_LABELS,
    ORDER_STATUSES,
    Order,
    OrderItem,
)
from app.models.order_return import OrderReturn, OrderReturnItem
from app.models.product import Product
from app.models.stock_transfer import (
    StockTransfer,
    StockTransferItem,
)
from app.models.stocktake import Stocktake, StocktakeItem
from app.models.task import TASK_PRIORITIES, TASK_STATUSES, Task
from app.models.types import BIGINT_ID, BIGINT_UNSIGNED_ID
from app.models.user import User
from app.models.warehouse import Warehouse, WarehouseStock

__all__ = [
    "BIGINT_ID",
    "BIGINT_UNSIGNED_ID",
    "ORDER_STATUSES",
    "ORDER_STATUS_LABELS",
    "TASK_PRIORITIES",
    "TASK_STATUSES",
    "Category",
    "InventoryLog",
    "Order",
    "OrderItem",
    "OrderReturn",
    "OrderReturnItem",
    "Product",
    "StockTransfer",
    "StockTransferItem",
    "Stocktake",
    "StocktakeItem",
    "Task",
    "User",
    "Warehouse",
    "WarehouseStock",
]
