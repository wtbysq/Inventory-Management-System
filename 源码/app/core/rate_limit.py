"""接口限流。

算法：固定窗口计数（Fixed Window）。

    key = rl:{scope}:{客户端IP}
    第一次请求把计数设为 1 并设置窗口过期时间；
    窗口内每次请求计数 +1，超过阈值返回 429。

为什么用固定窗口？
    实现简单、性能好，对防刷足够。
    缺点是窗口边界可能被“打满两次”，如果需要更平滑的限流，
    可以换成滑动窗口或令牌桶。

计数存储复用 `app.core.cache`：
    有 Redis 时多进程共享计数，没有 Redis 时退化为单进程计数。
"""

from collections.abc import Callable

from fastapi import Request

from app.core.cache import cache
from app.core.config import settings
from app.core.exceptions import RateLimitError


def rate_limit(
    *,
    scope: str,
    limit: int | None = None,
    window_seconds: int | None = None,
) -> Callable[[Request], None]:
    """生成限流依赖。

    Args:
        scope: 限流作用域名称，不同接口用不同 scope，互不影响。
        limit: 窗口内允许的最大请求数，默认读取全局配置。
        window_seconds: 窗口长度（秒），默认读取全局配置。

    用法:
        @router.post(
            "/orders",
            dependencies=[Depends(rate_limit(scope="order_create", limit=30))],
        )
    """

    effective_limit = limit or settings.rate_limit_default_limit
    effective_window = window_seconds or settings.rate_limit_window_seconds

    def dependency(request: Request) -> None:
        """执行一次计数，超过阈值抛 429。"""
        if not settings.rate_limit_enabled:
            return

        # 客户端 IP：本地开发通常是 127.0.0.1；
        # 部署在 Nginx 后面时，需要配置 --proxy-headers 才能拿到真实 IP。
        client_ip = request.client.host if request.client else "unknown"
        key = f"rl:{scope}:{client_ip}"

        count = cache.incr(key, ttl=effective_window)
        if count > effective_limit:
            raise RateLimitError(
                f"请求过于频繁，请稍后再试：{scope} 每 "
                f"{effective_window} 秒最多 {effective_limit} 次"
            )

    return dependency
