"""订单支付、取消、退货流程测试。"""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inventory_log import InventoryLog
from app.models.order import Order
from app.models.product import Product
from app.models.warehouse import WarehouseStock


def _create_order(
    client: TestClient,
    product_id: int,
    quantity: int = 2,
) -> dict:
    """创建一个待支付订单。"""
    response = client.post(
        "/api/orders",
        json={
            "items": [{"product_id": product_id, "quantity": quantity}],
            "remark": "流程测试订单",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_pay_order(client: TestClient, sample_product: Product) -> None:
    """支付后状态变为 PAID，重复支付返回 409。"""
    order = _create_order(client, sample_product.id)

    response = client.post(
        f"/api/orders/{order['id']}/pay",
        json={"payment_method": "WECHAT"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PAID"
    assert data["payment_method"] == "WECHAT"
    assert data["paid_at"] is not None

    duplicate = client.post(
        f"/api/orders/{order['id']}/pay",
        json={},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "CONFLICT"


def test_cancel_order_restocks_inventory(
    client: TestClient,
    db_session: Session,
    sample_product: Product,
) -> None:
    """取消订单会回补库存并写入 IN 流水。"""
    order = _create_order(client, sample_product.id, quantity=3)

    db_session.refresh(sample_product)
    assert sample_product.quantity == 7

    response = client.post(
        f"/api/orders/{order['id']}/cancel",
        json={"reason": "客户改主意"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"
    assert data["cancel_reason"] == "客户改主意"

    db_session.refresh(sample_product)
    assert sample_product.quantity == 10

    # 默认仓库库存也回补到 10。
    stock = db_session.scalar(
        select(WarehouseStock).where(
            WarehouseStock.product_id == sample_product.id
        )
    )
    assert stock is not None
    assert stock.quantity == 10

    new_log = db_session.scalars(
        select(InventoryLog)
        .where(InventoryLog.product_id == sample_product.id)
        .order_by(InventoryLog.id.desc())
    ).first()
    assert new_log.change_type == "IN"
    assert new_log.change_quantity == 3

    # 重复取消应返回 409。
    duplicate = client.post(
        f"/api/orders/{order['id']}/cancel",
        json={},
    )
    assert duplicate.status_code == 409


def test_partial_return_then_full_return(
    client: TestClient,
    db_session: Session,
    sample_product: Product,
) -> None:
    """支持部分退货，退完后订单状态为 RETURNED。"""
    order = _create_order(client, sample_product.id, quantity=3)
    client.post(f"/api/orders/{order['id']}/pay", json={})

    order_item = order["items"][0]

    # 第一次退 1 件。
    first = client.post(
        f"/api/orders/{order['id']}/returns",
        json={
            "items": [
                {
                    "order_item_id": order_item["id"],
                    "quantity": 1,
                }
            ],
            "reason": "尺码不合适",
        },
    )
    assert first.status_code == 201
    first_data = first.json()
    assert first_data["refund_amount"] == "99.00"
    assert first_data["items"][0]["quantity"] == 1

    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["status"] == "PARTIALLY_RETURNED"
    assert Decimal(detail["refunded_amount"]) == Decimal("99.00")
    assert detail["items"][0]["returned_quantity"] == 1

    db_session.refresh(sample_product)
    assert sample_product.quantity == 8

    # 第二次退剩余 2 件。
    second = client.post(
        f"/api/orders/{order['id']}/returns",
        json={
            "items": [
                {
                    "order_item_id": order_item["id"],
                    "quantity": 2,
                }
            ]
        },
    )
    assert second.status_code == 201
    assert second.json()["refund_amount"] == "198.00"

    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["status"] == "RETURNED"
    assert Decimal(detail["refunded_amount"]) == Decimal("297.00")

    # 退货记录应有 2 条。
    returns = client.get(f"/api/orders/{order['id']}/returns").json()
    assert len(returns) == 2

    # 再退一次应返回 409。
    extra = client.post(
        f"/api/orders/{order['id']}/returns",
        json={
            "items": [
                {
                    "order_item_id": order_item["id"],
                    "quantity": 1,
                }
            ]
        },
    )
    assert extra.status_code == 409
    assert extra.json()["code"] == "CONFLICT"


def test_return_more_than_purchased_is_rejected(
    client: TestClient,
    db_session: Session,
    sample_product: Product,
) -> None:
    """单次退货数量超过购买数量时整单回滚。"""
    order = _create_order(client, sample_product.id, quantity=1)
    client.post(f"/api/orders/{order['id']}/pay", json={})

    response = client.post(
        f"/api/orders/{order['id']}/returns",
        json={
            "items": [
                {
                    "order_item_id": order["items"][0]["id"],
                    "quantity": 5,
                }
            ]
        },
    )

    assert response.status_code == 409

    db_session.refresh(sample_product)
    assert sample_product.quantity == 9
    assert db_session.scalar(select(func.count(Order.id))) == 1


def test_cannot_return_unpaid_order(
    client: TestClient,
    sample_product: Product,
) -> None:
    """未支付订单不允许退货。"""
    order = _create_order(client, sample_product.id)

    response = client.post(
        f"/api/orders/{order['id']}/returns",
        json={
            "items": [
                {
                    "order_item_id": order["items"][0]["id"],
                    "quantity": 1,
                }
            ]
        },
    )

    assert response.status_code == 409
