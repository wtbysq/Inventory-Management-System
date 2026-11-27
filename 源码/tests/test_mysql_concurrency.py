r"""真实 MySQL 并发下单测试（默认跳过）。

SQLite 不支持真正的 `SELECT ... FOR UPDATE` 行锁，
只有连接真实 MySQL/InnoDB 才能验证“高并发下不超卖”。

运行方式:
    # PowerShell
    $env:MYSQL_TEST_URL = "mysql+pymysql://root:密码@localhost:3306/库存管理系统_test?charset=utf8mb4"
    .\.venv\Scripts\python.exe -m pytest tests/test_mysql_concurrency.py -v

注意:
    请指向独立的测试库，测试会创建表并清理自己写入的数据。
"""

import os
import threading
import time
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401  注册全部 ORM 模型
from app.core.exceptions import InsufficientStockError
from app.db import Base
from app.models.category import Category
from app.models.inventory_log import InventoryLog
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.warehouse import WarehouseStock
from app.repositories.warehouse_repo import WarehouseRepository
from app.schemas.order import OrderItemCreate
from app.services.order_service import OrderService

MYSQL_URL = os.getenv("MYSQL_TEST_URL")

pytestmark = pytest.mark.skipif(
    not MYSQL_URL,
    reason="未设置 MYSQL_TEST_URL，跳过真实 MySQL 并发测试",
)


def test_concurrent_orders_do_not_oversell() -> None:
    """20 个线程同时抢购库存 10 的商品，只能成功 10 单。"""
    assert MYSQL_URL

    engine = create_engine(
        MYSQL_URL,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=10,
    )
    # 只创建缺失的表，不会删除已有数据。
    Base.metadata.create_all(bind=engine)

    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    run_id = f"test{int(time.time())}"
    product_id: int | None = None
    category_id: int | None = None

    try:
        # ------------------------------------------------------------------
        # 准备数据
        # ------------------------------------------------------------------
        with session_factory() as db:
            category = Category(
                category_name=f"并发测试-{run_id}"[:32],
                sku_prefix=run_id[-6:].upper(),
            )
            db.add(category)
            db.flush()

            product = Product(
                category_id=category.id,
                product_name="并发测试商品",
                sku=f"CC-{run_id}",
                quantity=10,
                price=Decimal("10.00"),
                cost=Decimal("5.00"),
                unit="件",
                low_stock_threshold=1,
            )
            db.add(product)
            db.flush()

            # 提前创建默认仓库和仓库库存，
            # 避免并发时多个事务同时插入同一条仓库记录触发唯一约束。
            warehouse_repo = WarehouseRepository(db)
            warehouse_repo.ensure_default_stock(product)
            db.commit()

            product_id = product.id
            category_id = category.id

        # ------------------------------------------------------------------
        # 并发下单
        # ------------------------------------------------------------------
        concurrency = 20
        results: list[str] = []
        results_lock = threading.Lock()
        barrier = threading.Barrier(concurrency, timeout=60)

        def worker() -> None:
            """每个线程用独立 Session 下一单。"""
            db = session_factory()
            try:
                # 等所有线程就绪后同一时刻发起请求，模拟并发抢购。
                barrier.wait()
                OrderService(db).create_order(
                    items=[
                        OrderItemCreate(
                            product_id=product_id,
                            quantity=1,
                        )
                    ],
                    operator=run_id,
                    remark="并发测试",
                )
                outcome = "ok"
            except InsufficientStockError:
                outcome = "insufficient"
            except Exception as exc:  # noqa: BLE001 - 记录非预期异常
                outcome = f"error:{exc}"
            finally:
                db.close()

            with results_lock:
                results.append(outcome)

        threads = [
            threading.Thread(target=worker)
            for _ in range(concurrency)
        ]
        started_at = time.perf_counter()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        elapsed = time.perf_counter() - started_at

        # ------------------------------------------------------------------
        # 断言
        # ------------------------------------------------------------------
        errors = [item for item in results if item.startswith("error")]
        assert errors == [], f"出现非预期异常: {errors}"

        success = results.count("ok")
        insufficient = results.count("insufficient")

        assert success == 10, f"应该成功 10 单，实际 {success}"
        assert insufficient == 10, f"应该失败 10 单，实际 {insufficient}"

        with session_factory() as db:
            product = db.get(Product, product_id)
            assert product is not None
            # 核心断言：库存不能变成负数，也不能多扣。
            assert product.quantity == 0

            order_count = db.scalar(
                select(func.count(Order.id)).where(
                    Order.operator == run_id
                )
            )
            assert order_count == 10

            # 每个成功订单生成 1 条出库流水。
            log_count = db.scalar(
                select(func.count(InventoryLog.id)).where(
                    InventoryLog.product_id == product_id,
                    InventoryLog.change_type == "OUT",
                )
            )
            assert log_count == 10

        print(
            f"\n并发测试完成：{concurrency} 个请求，成功 {success}，"
            f"库存不足 {insufficient}，耗时 {elapsed:.2f}s"
        )

    finally:
        # ------------------------------------------------------------------
        # 清理本次测试写入的数据（按外键依赖顺序删除）
        # ------------------------------------------------------------------
        with session_factory() as db:
            if product_id is not None:
                order_ids = db.scalars(
                    select(Order.id).where(Order.operator == run_id)
                ).all()
                if order_ids:
                    db.execute(
                        delete(OrderItem).where(
                            OrderItem.order_id.in_(order_ids)
                        )
                    )
                    db.execute(
                        delete(Order).where(Order.id.in_(order_ids))
                    )
                db.execute(
                    delete(InventoryLog).where(
                        InventoryLog.product_id == product_id
                    )
                )
                db.execute(
                    delete(WarehouseStock).where(
                        WarehouseStock.product_id == product_id
                    )
                )
                db.execute(
                    delete(Product).where(Product.id == product_id)
                )
            if category_id is not None:
                db.execute(
                    delete(Category).where(Category.id == category_id)
                )
            db.commit()

        engine.dispose()
