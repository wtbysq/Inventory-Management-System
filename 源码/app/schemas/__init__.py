"""Pydantic 请求与响应模型。"""

from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    TokenOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.schemas.category import CategoryOut
from app.schemas.common import PageResponse
from app.schemas.inventory import InventoryChangeRequest, InventoryLogOut
from app.schemas.order import (
    OrderCancelRequest,
    OrderCreate,
    OrderItemCreate,
    OrderItemOut,
    OrderOut,
    OrderPayRequest,
    OrderReturnCreate,
    OrderReturnItemCreate,
    OrderReturnItemOut,
    OrderReturnOut,
    OrderStats,
)
from app.schemas.product import ProductOut, ProductStats
from app.schemas.stocktake import (
    StocktakeCountItem,
    StocktakeCountRequest,
    StocktakeCreate,
    StocktakeItemOut,
    StocktakeOut,
)
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate
from app.schemas.transfer import (
    TransferCreate,
    TransferItemCreate,
    TransferItemOut,
    TransferOut,
    WarehouseBrief,
    WarehouseCreate,
    WarehouseOut,
)

__all__ = [
    "ChangePasswordRequest",
    "CategoryOut",
    "InventoryChangeRequest",
    "InventoryLogOut",
    "LoginRequest",
    "OrderCancelRequest",
    "OrderCreate",
    "OrderItemCreate",
    "OrderItemOut",
    "OrderOut",
    "OrderPayRequest",
    "OrderReturnCreate",
    "OrderReturnItemCreate",
    "OrderReturnItemOut",
    "OrderReturnOut",
    "OrderStats",
    "PageResponse",
    "ProductOut",
    "ProductStats",
    "StocktakeCountItem",
    "StocktakeCountRequest",
    "StocktakeCreate",
    "StocktakeItemOut",
    "StocktakeOut",
    "TaskCreate",
    "TaskOut",
    "TaskUpdate",
    "TokenOut",
    "TransferCreate",
    "TransferItemCreate",
    "TransferItemOut",
    "TransferOut",
    "UserCreate",
    "UserOut",
    "UserUpdate",
    "WarehouseBrief",
    "WarehouseCreate",
    "WarehouseOut",
]
