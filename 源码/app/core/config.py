"""集中式应用配置。

所有可调参数都放在这里，由 pydantic-settings 从环境变量或项目根目录的
`.env` 读取。这样做的好处是：

1. 代码里不再散落魔法数字（例如 token 有效期、缓存时间、限流阈值）。
2. 测试可以通过 fixture 直接修改 `settings` 对象的属性，临时关掉缓存或限流。
3. 部署时只需要改 `.env`，不用改代码。

环境变量名与字段名大小写无关，例如：

    DATABASE_URL=mysql+pymysql://root:password@localhost:3306/库存管理系统?charset=utf8mb4
    SECRET_KEY=请换成随机长字符串
    CACHE_ENABLED=true
    REDIS_URL=redis://127.0.0.1:6379/0
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """项目全部配置项。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # 数据库
    # ------------------------------------------------------------------
    # 本机 MySQL 默认库名“库存管理系统”。
    # 真实密码不要写进代码，请在项目根目录的 .env 中用 DATABASE_URL 覆盖。
    database_url: str = (
        "mysql+pymysql://root:password@localhost:3306/库存管理系统?charset=utf8mb4"
    )
    db_echo: bool = False

    # 真实 MySQL 并发测试使用的连接串，留空则跳过该测试。
    # 建议指向一个独立的测试库，测试会清理自己的数据。
    mysql_test_url: str = (
        "mysql+pymysql://root:password@localhost:3306/库存管理系统_test?charset=utf8mb4"
    )

    # ------------------------------------------------------------------
    # 登录与权限（JWT）
    # ------------------------------------------------------------------
    # 生产环境必须通过 .env 覆盖成随机字符串，否则 token 可被伪造。
    secret_key: str = "dev-secret-key-change-me-in-production"
    # access_token 有效期，单位分钟，默认 12 小时。
    access_token_expire_minutes: int = 720
    # PBKDF2 迭代次数。数值越大越安全，但登录时 CPU 开销也越大。
    password_hash_iterations: int = 120_000

    # 是否在服务启动时自动创建默认管理员（仅当用户表为空时）。
    bootstrap_admin: bool = True
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # ------------------------------------------------------------------
    # Redis 缓存
    # ------------------------------------------------------------------
    redis_url: str = "redis://127.0.0.1:6379/0"
    # 缓存默认关闭：测试环境必须关闭，生产环境建议通过 .env 打开。
    cache_enabled: bool = False
    # 缓存有效期，单位秒。
    cache_ttl_seconds: int = 30

    # ------------------------------------------------------------------
    # 接口限流
    # ------------------------------------------------------------------
    rate_limit_enabled: bool = True
    # 普通接口默认额度：每个窗口 300 次。
    rate_limit_default_limit: int = 300
    # 限流窗口，单位秒。
    rate_limit_window_seconds: int = 60


# 全局唯一配置对象。
# 注意：pytest 中可以直接修改它的属性来关闭缓存 / 限流。
settings = Settings()
