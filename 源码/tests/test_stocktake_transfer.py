"""库存盘点与仓库调拨测试。"""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory_log import InventoryLog
from app.models.product import Product
from app.models.warehouse import Warehouse, WarehouseStock


def test_stocktake_adjusts_inventory(
    client: TestClient,
    db_session: Session,
    sample_product: Product,
) -> None:
    """盘点确认后库存被改成实盘数量，并生成 ADJUST 流水。"""
    created = client.post("/api/stocktakes", json={"remark": "月末盘点"})
    assert created.status_code == 201

    stocktake = created.json()
    assert stocktake["status"] == "COUNTING"
    assert len(stocktake["items"]) == 1
    assert stocktake["items"][0]["expected_quantity"] == 10

    counted = client.post(
        f"/api/stocktakes/{stocktake['id']}/count",
        json={
            "items": [
                {
                    "product_id": sample_product.id,
                    "counted_quantity": 7,
                    "remark": "破损 3 件",
                }
            ]
        },
    )
    assert counted.status_code == 200
    assert counted.json()["items"][0]["difference"] == -3

    confirmed = client.post(f"/api/stocktakes/{stocktake['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"

    db_session.refresh(sample_product)
    assert sample_product.quantity == 7

    adjust_log = db_session.scalars(
        select(InventoryLog).where(InventoryLog.change_type == "ADJUST")
    ).first()
    assert adjust_log is not None
    assert adjust_log.change_quantity == 3
    assert adjust_log.before_quantity == 10
    assert adjust_log.after_quantity == 7

    # 默认仓库库存同步为 7。
    stock = db_session.scalar(
        select(WarehouseStock).where(
            WarehouseStock.product_id == sample_product.id
        )
    )
    assert stock is not None
    assert stock.quantity == 7

    # 已确认的盘点单不允许再次确认。
    again = client.post(f"/api/stocktakes/{stocktake['id']}/confirm")
    assert again.status_code == 409


def test_cancel_stocktake_keeps_inventory(
    client: TestClient,
    db_session: Session,
    sample_product: Product,
) -> None:
    """取消盘点不会修改库存。"""
    created = client.post("/api/stocktakes", json={})
    stocktake_id = created.json()["id"]

    client.post(
        f"/api/stocktakes/{stocktake_id}/count",
        json={
            "items": [
                {"product_id": sample_product.id, "counted_quantity": 1}
            ]
        },
    )

    cancelled = client.post(f"/api/stocktakes/{stocktake_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"

    db_session.refresh(sample_product)
    assert sample_product.quantity == 10

    # 已取消的盘点单不能确认。
    confirm = client.post(f"/api/stocktakes/{stocktake_id}/confirm")
    assert confirm.status_code == 409


def test_transfer_moves_warehouse_stock(
    client: TestClient,
    db_session: Session,
    sample_product: Product,
) -> None:
    """调拨只改变仓库库存，不改变总库存。"""
    warehouses = client.get("/api/warehouses").json()
    assert len(warehouses) == 1
    main_id = warehouses[0]["id"]
    assert warehouses[0]["code"] == "MAIN"

    created = client.post(
        "/api/warehouses",
        json={"code": "wh-sh", "name": "上海仓", "address": "上海市"},
    )
    assert created.status_code == 201
    assert created.json()["code"] == "WH-SH"
    shanghai_id = created.json()["id"]

    transfer = client.post(
        "/api/transfers",
        json={
            "from_warehouse_id": main_id,
            "to_warehouse_id": shanghai_id,
            "items": [
                {"product_id": sample_product.id, "quantity": 4}
            ],
            "remark": "补货上海仓",
        },
    )
    assert transfer.status_code == 201, transfer.text
    data = transfer.json()
    assert data["status"] == "COMPLETED"
    assert data["items"][0]["quantity"] == 4
    assert data["from_warehouse"]["id"] == main_id

    db_session.refresh(sample_product)
    # 总库存不变。
    assert sample_product.quantity == 10

    stocks = {
        stock.warehouse_id: stock.quantity
        for stock in db_session.scalars(
            select(WarehouseStock).where(
                WarehouseStock.product_id == sample_product.id
            )
        )
    }
    assert stocks[main_id] == 6
    assert stocks[shanghai_id] == 4

    # 调出仓库存不足时返回 409，且不会产生新调拨单。
    failed = client.post(
        "/api/transfers",
        json={
            "from_warehouse_id": shanghai_id,
            "to_warehouse_id": main_id,
            "items": [
                {"product_id": sample_product.id, "quantity": 5}
            ],
        },
    )
    assert failed.status_code == 409

    listing = client.get("/api/transfers").json()
    assert listing["total"] == 1


def test_transfer_requires_different_warehouses(
    client: TestClient,
    sample_product: Product,
    db_session: Session,
) -> None:
    """调出和调入仓库相同时返回 422。"""
    main_id = client.get("/api/warehouses").json()[0]["id"]

    response = client.post(
        "/api/transfers",
        json={
            "from_warehouse_id": main_id,
            "to_warehouse_id": main_id,
            "items": [{"product_id": sample_product.id, "quantity": 1}],
        },
    )

    assert response.status_code == 422

    # 也不应该产生仓库记录之外的数据变化。
    warehouses = db_session.scalars(select(Warehouse)).all()
    assert len(warehouses) == 1
