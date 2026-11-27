"""FastAPI 接口测试。"""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.product import Product


def test_health_check(client: TestClient) -> None:
    """健康检查接口应返回 ok。"""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    # 同时返回缓存后端，便于确认 Redis 是否连接成功。
    assert data["cache_backend"] in {"redis", "memory"}


def test_root_page(client: TestClient) -> None:
    """首页应返回管理页面 HTML。"""
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "库存管理系统" in response.text


def test_static_assets(client: TestClient) -> None:
    """前端 CSS 和 JS 应能正常访问。"""
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_list_categories(
    client: TestClient,
    sample_product: Product,
) -> None:
    """分类接口应返回测试分类。"""
    response = client.get("/api/categories")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["category_name"] == "测试服装"
    assert data[0]["sku_prefix"] == "TEST"


def test_search_products_by_keyword(
    client: TestClient,
    sample_product: Product,
) -> None:
    """商品搜索应支持名称模糊匹配和分页。"""
    response = client.get(
        "/api/products",
        params={"keyword": "T恤", "page": 1, "size": 10},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["items"][0]["sku"] == "TEST-0001"


def test_product_stats(
    client: TestClient,
    sample_product: Product,
) -> None:
    """库存统计应正确计算数量和库存价值。"""
    response = client.get("/api/products/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["total_products"] == 1
    assert data["total_quantity"] == 10
    assert data["total_inventory_value"] == "500.00"
    assert data["low_stock_count"] == 0


def test_inbound_api(
    client: TestClient,
    db_session: Session,
    sample_product: Product,
) -> None:
    """入库接口应增加库存并返回流水。"""
    response = client.post(
        "/api/inventory/inbound",
        json={
            "product_id": sample_product.id,
            "quantity": 6,
            "operator": "api-tester",
            "remark": "接口入库",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["change_type"] == "IN"
    assert data["before_quantity"] == 10
    assert data["after_quantity"] == 16

    db_session.refresh(sample_product)
    assert sample_product.quantity == 16


def test_outbound_api_and_insufficient_stock(
    client: TestClient,
    db_session: Session,
    sample_product: Product,
) -> None:
    """出库成功返回 201，库存不足返回 409。"""
    success_response = client.post(
        "/api/inventory/outbound",
        json={
            "product_id": sample_product.id,
            "quantity": 4,
            "operator": "api-tester",
        },
    )

    assert success_response.status_code == 201
    assert success_response.json()["after_quantity"] == 6

    db_session.refresh(sample_product)
    assert sample_product.quantity == 6

    failed_response = client.post(
        "/api/inventory/outbound",
        json={
            "product_id": sample_product.id,
            "quantity": 999,
        },
    )

    assert failed_response.status_code == 409
    assert failed_response.json()["code"] == "INSUFFICIENT_STOCK"

    db_session.refresh(sample_product)
    assert sample_product.quantity == 6


def test_create_order_api(
    client: TestClient,
    db_session: Session,
    sample_product: Product,
) -> None:
    """创建订单接口应扣库存并返回订单明细。"""
    response = client.post(
        "/api/orders",
        json={
            "items": [
                {
                    "product_id": sample_product.id,
                    "quantity": 2,
                }
            ],
            "operator": "api-tester",
            "remark": "测试下单",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "CREATED"
    assert data["total_amount"] == "198.00"
    assert len(data["items"]) == 1
    assert data["items"][0]["sku"] == "TEST-0001"
    assert data["items"][0]["subtotal"] == "198.00"

    db_session.refresh(sample_product)
    assert sample_product.quantity == 8


def test_list_orders_api(
    client: TestClient,
    sample_product: Product,
) -> None:
    """订单列表接口应返回订单和明细。"""
    create_response = client.post(
        "/api/orders",
        json={
            "items": [
                {
                    "product_id": sample_product.id,
                    "quantity": 1,
                }
            ]
        },
    )
    assert create_response.status_code == 201

    response = client.get("/api/orders")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["order_no"].startswith("SO")
    assert len(data["items"][0]["items"]) == 1


def test_create_order_rejects_insufficient_stock_api(
    client: TestClient,
    db_session: Session,
    sample_product: Product,
) -> None:
    """订单中任一商品库存不足时返回 409，且不创建订单。"""
    response = client.post(
        "/api/orders",
        json={
            "items": [
                {
                    "product_id": sample_product.id,
                    "quantity": 999,
                }
            ]
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "INSUFFICIENT_STOCK"

    db_session.refresh(sample_product)
    assert sample_product.quantity == 10
    assert db_session.scalar(select(func.count(Order.id))) == 0
