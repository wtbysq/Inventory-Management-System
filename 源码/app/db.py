"""数据库连接、Session 和 ORM 基类。

配置项统一定义在 `app/core/config.py`，
这里只负责创建引擎和 Session 工厂。
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# 重新导出，保持 `from app.db import settings` 这种旧写法可用。
__all__ = ["Base", "SessionLocal", "engine", "get_db", "settings"]

engine = create_engine(
    settings.database_url,
    echo=settings.db_echo,
    # pool_pre_ping：从连接池取连接前先 ping 一次，
    # 避免 MySQL 8 小时空闲断开导致的 "MySQL server has gone away"。
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """所有 SQLAlchemy 模型的基类。"""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求创建 Session，请求结束后关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
