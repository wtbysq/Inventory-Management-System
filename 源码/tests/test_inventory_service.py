"""库存 Service 单元测试。"""

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientStockError
from app.models.product import Product
from app.services.inventory_service import InventoryService


def test_inbound_increases_quantity_and_creates_log(
    db_session: Session,
    sample_product: Product,
) -> None:
    """入库后库存增加，并生成一条 IN 流水。"""
    service = InventoryService(db_session)

    log = service.inbound(
        product_id=sample_product.id,
        quantity=5,
        operator="tester",
        remark="采购入库",
    )

    db_session.refresh(sample_product)

    assert sample_product.quantity == 15
    assert log.change_type == "IN"
    assert log.change_quantity == 5
    assert log.before_quantity == 10
    assert log.after_quantity == 15
    assert log.operator == "tester"

    logs, total = service.list_logs(
        product_id=sample_product.id,
        page=1,
        size=10,
    )
    assert total == 1
    assert logs[0].id == log.id


def test_outbound_decreases_quantity_and_creates_log(
    db_session: Session,
    sample_product: Product,
) -> None:
    """出库后库存减少，并生成一条 OUT 流水。"""
    service = InventoryService(db_session)

    log = service.outbound(
        product_id=sample_product.id,
        quantity=3,
        operator="tester",
        remark="销售出库",
    )

    db_session.refresh(sample_product)

    assert sample_product.quantity == 7
    assert log.change_type == "OUT"
    assert log.change_quantity == 3
    assert log.before_quantity == 10
    assert log.after_quantity == 7
    assert sample_product.last_outbound_at is not None


def test_outbound_rejects_insufficient_stock_and_rolls_back(
    db_session: Session,
    sample_product: Product,
) -> None:
    """库存不足时出库失败，库存保持不变且不生成流水。"""
    service = InventoryService(db_session)

    with pytest.raises(InsufficientStockError):
        service.outbound(
            product_id=sample_product.id,
            quantity=999,
        )

    db_session.refresh(sample_product)

    assert sample_product.quantity == 10

    logs, total = service.list_logs(
        product_id=sample_product.id,
        page=1,
        size=10,
    )
    assert total == 0
    assert logs == []


def test_inbound_rejects_zero_quantity(
    db_session: Session,
    sample_product: Product,
) -> None:
    """入库数量必须大于 0。"""
    service = InventoryService(db_session)

    with pytest.raises(Exception) as exc_info:
        service.inbound(product_id=sample_product.id, quantity=0)

    assert "数量必须大于 0" in str(exc_info.value)
