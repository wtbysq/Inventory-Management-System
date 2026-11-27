"""缓存抽象层：优先使用 Redis，Redis 不可用时自动降级为进程内缓存。

为什么需要降级？
    本地开发或演示环境可能没有启动 Redis。如果代码强依赖 Redis，
    一旦连不上，整个服务不可用，体验很差。
    这里的设计是：Redis 连不上就自动用内存字典，业务照常运行，
    只是多进程之间不共享缓存。

缓存内容:
    - 商品统计（商品种类、库存总量、库存价值、低库存数）
    - 订单经营统计（销售额、已支付订单数、累计利润）
    - 限流计数器（这个即使 cache_enabled=False 也会生效）

一致性策略:
    - 读接口写入缓存，设置较短 TTL（默认 30 秒）。
    - 任何写操作（入库、出库、下单、取消、退货、盘点、调拨）
      都会删除对应缓存 key，保证前端立刻看到新数据。
"""

import json
import logging
import threading
import time
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# redis 属于可选依赖：没安装时直接使用内存缓存。
try:  # pragma: no cover - 取决于运行环境是否安装 redis
    import redis as redis_lib
except ImportError:  # pragma: no cover
    redis_lib = None


# Redis key 统一前缀，避免和其他项目混用同一个 db。
KEY_PREFIX = "inventory:"

# 缓存 key 常量集中定义，避免手写字符串拼错。
CACHE_KEY_PRODUCT_STATS = "products:stats"
CACHE_KEY_ORDER_STATS = "orders:stats"


class _MemoryStore:
    """带过期时间的线程安全内存字典。

    TestClient / 多线程并发测试下也可能被同时访问，所以必须加锁。
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        """读取未过期的值，过期则顺手删除。"""
        now = time.time()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, ttl: int) -> None:
        """写入并记录过期时间。"""
        with self._lock:
            self._data[key] = (time.time() + ttl, value)

    def delete(self, key: str) -> None:
        """删除单个 key。"""
        with self._lock:
            self._data.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        """删除所有以 prefix 开头的 key。"""
        with self._lock:
            for key in [k for k in self._data if k.startswith(prefix)]:
                self._data.pop(key, None)

    def incr(self, key: str, ttl: int) -> int:
        """原子自增，用于限流计数。

        第一次自增时设置过期时间，之后只加 1。
        """
        now = time.time()
        with self._lock:
            item = self._data.get(key)
            if item is None or item[0] <= now:
                count = 1
                self._data[key] = (now + ttl, "1")
                return count
            count = int(item[1]) + 1
            self._data[key] = (item[0], str(count))
            return count

    def clear(self) -> None:
        """清空全部内存缓存。"""
        with self._lock:
            self._data.clear()


class Cache:
    """统一的缓存门面（Facade）。

    对外只暴露 get / set / delete / delete_prefix / incr 等简单方法，
    调用方不需要关心底层是 Redis 还是内存。
    """

    def __init__(self) -> None:
        self._memory = _MemoryStore()
        self._redis: Any | None = None
        self._redis_checked = False
        self._connect_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _client(self) -> Any | None:
        """懒加载 Redis 客户端。

        第一次使用时才尝试连接，避免应用启动时被 Redis 阻塞。
        连接失败后标记为不可用，后续请求直接走内存缓存。
        """
        if self._redis_checked:
            return self._redis

        with self._connect_lock:
            if self._redis_checked:
                return self._redis

            self._redis_checked = True
            if redis_lib is None or not settings.redis_url:
                logger.info("未安装 redis 客户端，缓存使用进程内内存实现")
                return None

            try:
                client = redis_lib.Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=0.3,
                    socket_timeout=0.3,
                )
                client.ping()
                self._redis = client
                logger.info("Redis 缓存已连接: %s", settings.redis_url)
            except Exception as exc:  # noqa: BLE001 - 任何连接问题都降级
                logger.info("Redis 不可用，已降级为内存缓存: %s", exc)
                self._redis = None

            return self._redis

    @property
    def backend(self) -> str:
        """返回当前实际使用的后端名称，便于在健康检查中展示。"""
        return "redis" if self._client() is not None else "memory"

    # ------------------------------------------------------------------
    # 字符串读写
    # ------------------------------------------------------------------
    def get(self, key: str) -> str | None:
        """读取缓存；缓存开关关闭时始终返回 None。"""
        if not settings.cache_enabled:
            return None

        full_key = KEY_PREFIX + key
        client = self._client()
        if client is not None:
            try:
                return client.get(full_key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis 读取失败，降级内存缓存: %s", exc)
                self._redis = None
                self._redis_checked = True

        return self._memory.get(full_key)

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """写入缓存；缓存开关关闭时什么也不做。"""
        if not settings.cache_enabled:
            return

        full_key = KEY_PREFIX + key
        ttl = ttl or settings.cache_ttl_seconds

        client = self._client()
        if client is not None:
            try:
                client.set(full_key, value, ex=ttl)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis 写入失败，降级内存缓存: %s", exc)
                self._redis = None
                self._redis_checked = True

        self._memory.set(full_key, value, ttl)

    def delete(self, *keys: str) -> None:
        """删除一个或多个缓存 key。"""
        for key in keys:
            full_key = KEY_PREFIX + key
            client = self._client()
            if client is not None:
                try:
                    client.delete(full_key)
                except Exception:  # noqa: BLE001
                    self._redis = None
                    self._redis_checked = True
            self._memory.delete(full_key)

    def delete_prefix(self, prefix: str) -> None:
        """删除某个前缀下的全部缓存。"""
        full_prefix = KEY_PREFIX + prefix
        client = self._client()
        if client is not None:
            try:
                # 使用 scan_iter 而不是 keys，避免阻塞 Redis。
                for key in client.scan_iter(match=full_prefix + "*"):
                    client.delete(key)
            except Exception:  # noqa: BLE001
                self._redis = None
                self._redis_checked = True
        self._memory.delete_prefix(full_prefix)

    def incr(self, key: str, ttl: int) -> int:
        """自增计数并返回当前值，用于接口限流。

        注意：这里不受 cache_enabled 控制，
        因为限流属于安全能力，而不是性能优化。
        """
        full_key = KEY_PREFIX + key
        client = self._client()
        if client is not None:
            try:
                # pipeline 保证 INCR 和 EXPIRE 一起执行。
                pipe = client.pipeline(transaction=True)
                pipe.incr(full_key)
                pipe.expire(full_key, ttl)
                count, _ = pipe.execute()
                return int(count)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis 计数失败，降级内存缓存: %s", exc)
                self._redis = None
                self._redis_checked = True

        return self._memory.incr(full_key, ttl)

    def clear(self) -> None:
        """清空缓存，测试和调试时使用。"""
        self._memory.clear()
        client = self._client()
        if client is not None:
            try:
                for key in client.scan_iter(match=KEY_PREFIX + "*"):
                    client.delete(key)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # JSON 便捷方法
    # ------------------------------------------------------------------
    def get_json(self, key: str) -> Any | None:
        """读取并反序列化 JSON；读取失败按未命中处理。"""
        raw = self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        """序列化后写入缓存。"""
        try:
            payload = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return
        self.set(key, payload, ttl=ttl)


# 全局缓存对象，全应用共享。
cache = Cache()
