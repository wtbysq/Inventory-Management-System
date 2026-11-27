"""路由/控制器层。"""

from app.controllers.auth_controller import router as auth_router
from app.controllers.category_controller import router as category_router
from app.controllers.inventory_controller import router as inventory_router
from app.controllers.order_controller import router as order_router
from app.controllers.product_controller import router as product_router
from app.controllers.stocktake_controller import router as stocktake_router
from app.controllers.task_controller import router as task_router
from app.controllers.transfer_controller import (
    router as transfer_router,
    warehouse_router,
)
from app.controllers.user_controller import router as user_router

__all__ = [
    "auth_router",
    "category_router",
    "inventory_router",
    "order_router",
    "product_router",
    "stocktake_router",
    "task_router",
    "transfer_router",
    "user_router",
    "warehouse_router",
]
