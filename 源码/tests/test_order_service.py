"""订单 Service 单元测试。"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientStockError
from app.models.inventory_log import InventoryLog
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.schemas.order import OrderItemCreate
from app.services.order_service import OrderService


def _create_second_product(
    db_session: Session,
    category_id: int,
) -> Product:
    """创建一个用于多商品订单测试的商品。"""
    product = Product(
        category_id=category_id,
        product_name="测试裤子",
        sku="TEST-0002",
        quantity=5,
        price=Decimal("50.00"),
        cost=Decimal("20.00"),
        unit="件",
        low_stock_threshold=2,
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


def test_create_order_deducts_stock_and_creates_details(
    db_session: Session,
    sample_product: Product,
) -> None:
    """下单成功后扣库存、生成订单明细和出库流水。"""
    service = OrderService(db_session)

    order = service.create_order(
        items=[
            OrderItemCreate(
                product_id=sample_product.id,
                quantity=3,
            )
        ],
        operator="tester",
        remark="测试订单",
    )

    db_session.refresh(sample_product)

    assert sample_product.quantity == 7
    assert order.status == "CREATED"
    assert order.total_amount == Decimal("297.00")
    assert len(order.items) == 1

    item = order.items[0]
    assert item.sku == "TEST-0001"
    assert item.quantity == 3
    assert item.unit_price == Decimal("99.00")
    assert item.subtotal == Decimal("297.00")

    logs = list(
        db_session.scalars(
            select(InventoryLog).where(
                InventoryLog.product_id == sample_product.id
            )
        ).all()
    )
    assert len(logs) == 1
    assert logs[0].change_type == "OUT"
    assert logs[0].change_quantity == 3
    assert logs[0].before_quantity == 10
    assert logs[0].after_quantity == 7


def test_create_order_merges_duplicate_product_rows(
    db_session: Session,
    sample_product: Product,
) -> None:
    """同一商品提交多行时，应合并数量后只扣一次库存。"""
    service = OrderService(db_session)

    order = service.create_order(
        items=[
            OrderItemCreate(
                product_id=sample_product.id,
                quantity=1,
            ),
            OrderItemCreate(
                product_id=sample_product.id,
                quantity=2,
            ),
        ],
    )

    db_session.refresh(sample_product)

    assert sample_product.quantity == 7
    assert len(order.items) == 1
    assert order.items[0].quantity == 3
    assert order.total_amount == Decimal("297.00")


def test_create_order_with_multiple_products(
    db_session: Session,
    sample_product: Product,
) -> None:
    """多商品订单应分别扣减库存并计算总金额。"""
    second_product = _create_second_product(
        db_session,
        sample_product.category_id,
    )
    service = OrderService(db_session)

    order = service.create_order(
        items=[
            OrderItemCreate(
                product_id=sample_product.id,
                quantity=1,
            ),
            OrderItemCreate(
                product_id=second_product.id,
                quantity=2,
            ),
        ],
    )

    db_session.refresh(sample_product)
    db_session.refresh(second_product)

    assert sample_product.quantity == 9
    assert second_product.quantity == 3
    assert order.total_amount == Decimal("199.00")
    assert len(order.items) == 2


def test_create_order_rejects_insufficient_stock_and_rolls_back(
    db_session: Session,
    sample_product: Product,
) -> None:
    """任一商品库存不足时，整个订单回滚。"""
    service = OrderService(db_session)

    with pytest.raises(InsufficientStockError):
        service.create_order(
            items=[
                OrderItemCreate(
                    product_id=sample_product.id,
                    quantity=999,
                )
            ],
        )

    db_session.refresh(sample_product)

    assert sample_product.quantity == 10
    assert db_session.scalar(select(func.count(Order.id))) == 0
    assert db_session.scalar(select(func.count(OrderItem.id))) == 0
    assert db_session.scalar(select(func.count(InventoryLog.id))) == 0


def test_list_orders(
    db_session: Session,
    sample_product: Product,
) -> None:
    """订单列表应返回订单和明细。"""
    service = OrderService(db_session)

    created_order = service.create_order(
        items=[
            OrderItemCreate(
                product_id=sample_product.id,
                quantity=2,
            )
        ],
    )

    orders, total = service.list_orders(page=1, size=10)

    assert total == 1
    assert orders[0].id == created_order.id
    assert len(orders[0].items) == 1
