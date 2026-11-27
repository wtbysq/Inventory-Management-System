r"""FastAPI 应用入口。

启动方式:
    .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

启动后:
    Swagger 文档: http://127.0.0.1:8000/docs
    ReDoc 文档:   http://127.0.0.1:8000/redoc
    管理页面:     http://127.0.0.1:8000/
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.controllers import (
    auth_router,
    category_router,
    inventory_router,
    order_router,
    product_router,
    stocktake_router,
    task_router,
    transfer_router,
    user_router,
    warehouse_router,
)
from app.core.cache import cache
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.services.auth_service import bootstrap_default_admin

logger = logging.getLogger(__name__)

# 管理页面静态资源目录。
# PyInstaller 打包后 __file__ 位于临时解压目录，静态文件需要通过 --add-data 一起打包。
_BUILTIN_STATIC_DIR = Path(__file__).resolve().parent / "static"


def _resolve_static_dir() -> Path:
    """解析前端静态资源目录。

    exe 运行时按顺序查找，命中即用：
        1. exe 同目录的 ``static/``          —— 分发到其他电脑时把前端放这里；
        2. exe 同目录的 ``app/static/``      —— exe 放在项目根目录时直接复用源码；
        3. 打包进 exe 的内置静态文件         —— 兜底，脱离源码也能运行。

    这样 exe 可以直接放在项目根目录双击启动，
    改前端后刷新页面即可生效，不必重新打包。
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        for candidate in (base / "static", base / "app" / "static"):
            if (candidate / "index.html").is_file():
                return candidate
    return _BUILTIN_STATIC_DIR


STATIC_DIR = _resolve_static_dir()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期钩子。

    启动时:
        - 如果用户表为空，自动创建默认管理员（可通过 BOOTSTRAP_ADMIN=false 关闭）。
        - 打印缓存后端，方便确认 Redis 是否连接成功。
    关闭时:
        - 无需特殊处理，连接池由 SQLAlchemy 管理。
    """
    logger.info("缓存后端: %s", cache.backend)

    if settings.bootstrap_admin:
        bootstrap_default_admin()

    yield


app = FastAPI(
    title="库存管理系统 API",
    description=(
        "基于 FastAPI + SQLAlchemy + MySQL 的库存管理系统。\n\n"
        "采用 Controller -> Service -> Repository 分层架构，"
        "支持商品、库存、订单（支付/取消/退货）、任务管理、"
        "库存盘点、仓库调拨、用户登录与角色权限。\n\n"
        "### 认证方式\n"
        "1. 调用 `POST /api/auth/login` 获取 access_token；\n"
        "2. 点击右上角 Authorize 按钮填入 token，"
        "或请求头携带 `Authorization: Bearer <token>`。\n\n"
        "### 角色\n"
        "- `admin` 管理员：全部功能 + 用户管理\n"
        "- `operator` 操作员：业务数据读写\n"
        "- `viewer` 只读用户：只能查询\n\n"
        "管理页面：http://127.0.0.1:8000/"
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# 前后端分离开发时允许跨域。
# 生产环境请把 allow_origins 改成实际前端域名。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册全局业务异常处理器。
register_exception_handlers(app)


@app.middleware("http")
async def no_cache_for_frontend(request: Request, call_next):
    """首页与前端静态资源禁用浏览器缓存。

    浏览器对没有 Cache-Control 的响应会做启发式缓存，
    导致更新前端后用户不强制刷新就一直看到旧页面。
    这里显式声明不缓存，保证每次刷新都拿到最新文件。
    """
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


# 挂载前端静态资源。
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 所有业务接口统一挂在 /api 下。
app.include_router(auth_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(category_router, prefix="/api")
app.include_router(product_router, prefix="/api")
app.include_router(inventory_router, prefix="/api")
app.include_router(order_router, prefix="/api")
app.include_router(task_router, prefix="/api")
app.include_router(stocktake_router, prefix="/api")
app.include_router(transfer_router, prefix="/api")
app.include_router(warehouse_router, prefix="/api")


@app.get("/", include_in_schema=False)
def root():
    """返回库存管理系统网页界面。"""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["系统"], summary="健康检查")
def health_check():
    """用于检查服务是否正常启动，同时返回当前缓存后端。"""
    return {
        "status": "ok",
        "cache_backend": cache.backend,
        "cache_enabled": settings.cache_enabled,
    }
