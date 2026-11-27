"""PyTest 公共夹具。"""

from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  确保所有 ORM 模型被注册
from app.core.config import settings
from app.core.security import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    get_current_user,
    hash_password,
)
from app.db import Base, get_db
from app.main import app
from app.models.category import Category
from app.models.product import Product
from app.models.user import User

# 测试环境关闭这些“环境相关”的能力，保证用例可重复：
# - 不要在测试里连接真实 MySQL 去初始化管理员；
# - 关闭缓存，避免上一个用例的统计结果污染下一个用例；
# - 关闭限流，避免大量测试请求触发 429（限流本身有单独用例）。
settings.bootstrap_admin = False
settings.cache_enabled = False
settings.rate_limit_enabled = False


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """为每个测试创建独立的内存 SQLite 数据库。

    使用 StaticPool 让内存数据库在多个连接之间共享，
    避免 FastAPI TestClient 与服务层拿到不同数据库连接。
    """
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = testing_session_local()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def admin_user(db_session: Session) -> User:
    """创建一个管理员用户，供接口测试默认登录。"""
    user = User(
        username="admin",
        password_hash=hash_password("admin123"),
        full_name="系统管理员",
        role=ROLE_ADMIN,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def viewer_user(db_session: Session) -> User:
    """创建一个只读用户，用于权限测试。"""
    user = User(
        username="viewer",
        password_hash=hash_password("viewer123"),
        full_name="只读用户",
        role=ROLE_VIEWER,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def client(
    db_session: Session,
    admin_user: User,
) -> Generator[TestClient, None, None]:
    """FastAPI 测试客户端。

    两处依赖替换:
        1. get_db -> 测试 Session；
        2. get_current_user -> 固定返回管理员。

    这样原有接口测试不需要每个请求都带 token，
    需要验证“未登录 / 权限不足”的用例可以主动移除替换。
    """

    def override_get_db():
        """测试用数据库依赖。"""
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def anonymous_client(client: TestClient) -> TestClient:
    """不带默认登录用户的客户端，用于验证 401。"""
    app.dependency_overrides.pop(get_current_user, None)
    return client


@pytest.fixture()
def sample_product(db_session: Session) -> Product:
    """插入一个测试商品：库存 10，成本价 50，售价 99。"""
    category = Category(
        category_name="测试服装",
        sku_prefix="TEST",
    )
    db_session.add(category)
    db_session.flush()

    product = Product(
        category_id=category.id,
        product_name="测试T恤",
        sku="TEST-0001",
        quantity=10,
        price=Decimal("99.00"),
        cost=Decimal("50.00"),
        unit="件",
        low_stock_threshold=3,
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    return product
