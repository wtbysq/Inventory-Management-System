"""FastAPI 依赖注入。

Controller 不直接创建 Service，而是通过 Depends 获取，
这样测试时可以替换数据库 Session，也方便后续扩展。
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.auth_service import AuthService
from app.services.category_service import CategoryService
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService
from app.services.product_service import ProductService
from app.services.stocktake_service import StocktakeService
from app.services.task_service import TaskService
from app.services.transfer_service import TransferService, WarehouseService


def get_category_service(
    db: Session = Depends(get_db),
) -> CategoryService:
    """获取分类 Service。"""
    return CategoryService(db)


def get_product_service(
    db: Session = Depends(get_db),
) -> ProductService:
    """获取商品 Service。"""
    return ProductService(db)


def get_inventory_service(
    db: Session = Depends(get_db),
) -> InventoryService:
    """获取库存 Service。"""
    return InventoryService(db)


def get_order_service(
    db: Session = Depends(get_db),
) -> OrderService:
    """获取订单 Service。"""
    return OrderService(db)


def get_auth_service(
    db: Session = Depends(get_db),
) -> AuthService:
    """获取认证 Service。"""
    return AuthService(db)


def get_task_service(
    db: Session = Depends(get_db),
) -> TaskService:
    """获取任务 Service。"""
    return TaskService(db)


def get_stocktake_service(
    db: Session = Depends(get_db),
) -> StocktakeService:
    """获取盘点 Service。"""
    return StocktakeService(db)


def get_transfer_service(
    db: Session = Depends(get_db),
) -> TransferService:
    """获取调拨 Service。"""
    return TransferService(db)


def get_warehouse_service(
    db: Session = Depends(get_db),
) -> WarehouseService:
    """获取仓库 Service。"""
    return WarehouseService(db)
