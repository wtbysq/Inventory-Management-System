"""FastAPI 全局异常处理器。"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException


def register_exception_handlers(app: FastAPI) -> None:
    """把业务异常统一转换为 JSON 响应。

    Args:
        app: FastAPI 应用实例。

    统一响应格式:
        {
            "code": "INSUFFICIENT_STOCK",
            "message": "商品库存不足"
        }
    """

    @app.exception_handler(AppException)
    async def app_exception_handler(
        _request: Request,
        exc: AppException,
    ) -> JSONResponse:
        """处理 AppException 及其子类。"""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
            },
        )
