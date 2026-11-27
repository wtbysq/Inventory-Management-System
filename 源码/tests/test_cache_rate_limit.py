"""Redis 缓存与接口限流测试。

说明:
    测试环境默认关闭缓存和限流（见 conftest.py），
    这里用 monkeypatch 临时打开，验证相关代码路径。
    没有安装或启动 Redis 时，缓存会自动降级为内存实现，
    因此这些用例在纯内存环境下也能稳定通过。
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.cache import CACHE_KEY_PRODUCT_STATS, cache
from app.core.config import settings
from app.models.product import Product


def test_product_stats_cache_and_invalidation(
    client: TestClient,
    db_session: Session,
    sample_product: Product,
    monkeypatch,
) -> None:
    """统计接口命中缓存，库存变化后缓存自动失效。"""
    monkeypatch.setattr(settings, "cache_enabled", True)
    cache.clear()

    first = client.get("/api/products/stats")
    assert first.status_code == 200
    assert first.json()["total_quantity"] == 10

    # 第一次查询后应该写入了缓存。
    cached = cache.get_json(CACHE_KEY_PRODUCT_STATS)
    assert cached is not None
    assert cached["total_quantity"] == 10

    # 入库 5 件，写操作会删除统计缓存。
    inbound = client.post(
        "/api/inventory/inbound",
        json={"product_id": sample_product.id, "quantity": 5},
    )
    assert inbound.status_code == 201
    assert cache.get_json(CACHE_KEY_PRODUCT_STATS) is None

    second = client.get("/api/products/stats")
    assert second.json()["total_quantity"] == 15


def test_health_reports_cache_backend(client: TestClient) -> None:
    """健康检查返回当前缓存后端，方便确认 Redis 是否生效。"""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["cache_backend"] in {"redis", "memory"}


def test_login_rate_limit_returns_429(
    anonymous_client: TestClient,
    monkeypatch,
) -> None:
    """登录接口每分钟最多 10 次，第 11 次返回 429。"""
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    # 清空计数，避免其他登录用例影响本用例。
    cache.delete_prefix("rl:login:")

    statuses = []
    for index in range(11):
        response = anonymous_client.post(
            "/api/auth/login",
            json={"username": f"nobody-{index}", "password": "wrong"},
        )
        statuses.append(response.status_code)

    # 前 10 次是密码错误（401），第 11 次被限流（429）。
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
