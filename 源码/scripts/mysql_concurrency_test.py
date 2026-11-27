r"""真实 MySQL 并发下单压测脚本。

用途:
    验证 InnoDB 行锁是否真的能防止超卖。
    SQLite 不支持 SELECT ... FOR UPDATE，单元测试无法覆盖这一点。

用法（在项目根目录执行）:
    .\.venv\Scripts\python.exe scripts\mysql_concurrency_test.py ^
        --url "mysql+pymysql://root:密码@localhost:3306/库存管理系统?charset=utf8mb4" ^
        --stock 10 --requests 20

参数:
    --url        MySQL 连接串，默认读取 .env 中的 MYSQL_TEST_URL
    --stock      初始库存，默认 10
    --requests   并发请求数，默认 20
    --keep-data  保留测试数据，便于手工查看（默认会自动清理）

输出示例:
    ==================================================
    并发请求: 20 | 初始库存: 10
    成功: 10 | 库存不足: 10 | 其他异常: 0
    最终库存: 0 | 订单数: 10 | 出库流水: 10
    结论: 通过，未出现超卖
    ==================================================

建议:
    使用独立的测试库，脚本会在其中创建缺失的表，并在结束时删除
    本次创建的测试商品、订单和流水。
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path

# 允许直接运行 scripts/ 下的脚本：把项目根目录加入 import 路径。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, delete, func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models  # noqa: E402,F401  注册全部模型
from app.core.config import settings  # noqa: E402
from app.core.exceptions import InsufficientStockError  # noqa: E402
from app.db import Base  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.inventory_log import InventoryLog  # noqa: E402
from app.models.order import Order, OrderItem  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.warehouse import WarehouseStock  # noqa: E402
from app.repositories.warehouse_repo import WarehouseRepository  # noqa: E402
from app.schemas.order import OrderItemCreate  # noqa: E402
from app.services.order_service import OrderService  # noqa: E402


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="真实 MySQL 并发下单测试：验证不会超卖",
    )
    parser.add_argument(
        "--url",
        default=settings.mysql_test_url,
        help="MySQL 连接串，默认取 .env 中的 MYSQL_TEST_URL",
    )
    parser.add_argument(
        "--stock",
        type=int,
        default=10,
        help="测试商品初始库存，默认 10",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=20,
        help="并发下单请求数，默认 20",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="保留测试数据，方便手工核对",
    )
    return parser.parse_args()


def run_concurrent_orders(url: str, stock: int, requests: int) -> dict:
    """执行并发下单并返回统计结果。"""
    engine = create_engine(
        url,
        pool_pre_ping=True,
        # 连接池需要足够支撑所有并发线程。
        pool_size=max(requests, 10),
        max_overflow=requests,
    )
    # 只创建缺失的表，不会影响已有数据。
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    run_id = f"bench{int(time.time())}"
    product_id: int | None = None
    category_id: int | None = None
    result: dict = {}

    try:
        # ------------------------------------------------------------------
        # 1. 准备商品和默认仓库库存
        # ------------------------------------------------------------------
        with session_factory() as db:
            category = Category(
                category_name=f"并发压测-{run_id}"[:32],
                sku_prefix=run_id[-6:].upper(),
            )
            db.add(category)
            db.flush()

            product = Product(
                category_id=category.id,
                product_name="并发压测商品",
                sku=f"BENCH-{run_id}",
                quantity=stock,
                price=Decimal("10.00"),
                cost=Decimal("5.00"),
                unit="件",
                low_stock_threshold=1,
            )
            db.add(product)
            db.flush()

            # 预先创建默认仓库库存，避免并发时重复插入触发唯一约束。
            WarehouseRepository(db).ensure_default_stock(product)
            db.commit()

            product_id = product.id
            category_id = category.id

        # ------------------------------------------------------------------
        # 2. 多线程同时下单
        # ------------------------------------------------------------------
        outcomes: list[str] = []
        outcomes_lock = threading.Lock()
        barrier = threading.Barrier(requests, timeout=120)

        def worker() -> None:
            """每个线程独立 Session、独立事务。"""
            db = session_factory()
            try:
                barrier.wait()
                OrderService(db).create_order(
                    items=[
                        OrderItemCreate(
                            product_id=product_id,
                            quantity=1,
                        )
                    ],
                    operator=run_id,
                    remark="并发压测",
                )
                outcome = "ok"
            except InsufficientStockError:
                outcome = "insufficient"
            except Exception as exc:  # noqa: BLE001
                outcome = f"error:{exc}"
            finally:
                db.close()

            with outcomes_lock:
                outcomes.append(outcome)

        threads = [
            threading.Thread(target=worker, name=f"worker-{i}")
            for i in range(requests)
        ]

        started_at = time.perf_counter()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        elapsed = time.perf_counter() - started_at

        # ------------------------------------------------------------------
        # 3. 校验结果
        # ------------------------------------------------------------------
        with session_factory() as db:
            product = db.get(Product, product_id)
            order_count = int(
                db.scalar(
                    select(func.count(Order.id)).where(
                        Order.operator == run_id
                    )
                )
                or 0
            )
            log_count = int(
                db.scalar(
                    select(func.count(InventoryLog.id)).where(
                        InventoryLog.product_id == product_id,
                        InventoryLog.change_type == "OUT",
                    )
                )
                or 0
            )

        result = {
            "requests": requests,
            "stock": stock,
            "success": outcomes.count("ok"),
            "insufficient": outcomes.count("insufficient"),
            "errors": [item for item in outcomes if item.startswith("error")],
            "elapsed": elapsed,
            "final_quantity": product.quantity if product else None,
            "order_count": order_count,
            "log_count": log_count,
            "product_id": product_id,
            "category_id": category_id,
            "run_id": run_id,
        }
        return result

    finally:
        if not getattr(run_concurrent_orders, "keep_data", False):
            _cleanup(session_factory, run_id, product_id, category_id)
        engine.dispose()


def _cleanup(session_factory, run_id: str, product_id, category_id) -> None:
    """删除本次压测写入的数据，保持数据库干净。"""
    with session_factory() as db:
        if product_id is not None:
            order_ids = db.scalars(
                select(Order.id).where(Order.operator == run_id)
            ).all()
            if order_ids:
                db.execute(
                    delete(OrderItem).where(OrderItem.order_id.in_(order_ids))
                )
                db.execute(delete(Order).where(Order.id.in_(order_ids)))

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
            db.execute(delete(Product).where(Product.id == product_id))

        if category_id is not None:
            db.execute(delete(Category).where(Category.id == category_id))

        db.commit()


def main() -> None:
    """脚本入口。"""
    args = parse_args()

    if args.stock <= 0 or args.requests <= 0:
        print("stock 和 requests 必须大于 0")
        raise SystemExit(1)

    print("=" * 56)
    print("真实 MySQL 并发下单测试")
    print(f"连接: {args.url}")
    print(f"并发请求: {args.requests} | 初始库存: {args.stock}")
    print("=" * 56)

    # 通过函数属性传递 --keep-data，避免修改函数签名。
    run_concurrent_orders.keep_data = args.keep_data  # type: ignore[attr-defined]

    result = run_concurrent_orders(
        url=args.url,
        stock=args.stock,
        requests=args.requests,
    )

    expected_success = min(result["stock"], result["requests"])
    passed = (
        not result["errors"]
        and result["success"] == expected_success
        and result["final_quantity"] is not None
        and result["final_quantity"] >= 0
        and result["final_quantity"] == result["stock"] - expected_success
    )

    print(f"成功: {result['success']} | 库存不足: {result['insufficient']} "
          f"| 其他异常: {len(result['errors'])}")
    print(f"最终库存: {result['final_quantity']} | "
          f"订单数: {result['order_count']} | "
          f"出库流水: {result['log_count']}")
    print(f"耗时: {result['elapsed']:.2f}s")

    if result["errors"]:
        print("异常详情:")
        for item in result["errors"][:5]:
            print(f"  - {item}")

    print("结论:", "通过，未出现超卖" if passed else "未通过，请检查")
    print("=" * 56)

    if args.keep_data:
        print(f"测试数据已保留：商品 ID {result['product_id']}，"
              f"操作人 {result['run_id']}")

    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
