"""业务异常定义。

分层架构中，Service 层不直接返回 HTTP 状态码，而是抛出业务异常；
由 Controller 层的全局异常处理器统一转换为 HTTP 响应。
"""


class AppException(Exception):
    """所有业务异常的基类。

    属性:
        status_code: 该异常对应的 HTTP 状态码。
        code: 业务错误码，方便前端根据错误码做不同处理。
        message: 给用户看的错误信息。
    """

    status_code: int = 400
    code: str = "APP_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(AppException):
    """资源不存在，例如商品 ID 查询不到。"""

    status_code = 404
    code = "NOT_FOUND"


class InsufficientStockError(AppException):
    """库存不足，出库数量大于当前库存时抛出。"""

    status_code = 409
    code = "INSUFFICIENT_STOCK"


class ValidationError(AppException):
    """业务参数校验失败，例如入库数量小于等于 0。"""

    status_code = 422
    code = "VALIDATION_ERROR"


class ConflictError(AppException):
    """状态冲突。

    典型场景:
        - 重复支付同一个订单
        - 取消一个已支付的订单
        - 退货数量超过可退数量
    """

    status_code = 409
    code = "CONFLICT"


class UnauthorizedError(AppException):
    """没有提供有效凭证，例如未登录或 token 过期。"""

    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppException):
    """已登录但权限不足，例如只读用户尝试创建订单。"""

    status_code = 403
    code = "FORBIDDEN"


class RateLimitError(AppException):
    """请求过于频繁，被限流组件拒绝。"""

    status_code = 429
    code = "RATE_LIMITED"
