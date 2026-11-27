# 依赖库与常用函数手册

这份文档分两部分：

1. **本项目用到的**——项目源码里真实出现的类、函数和写法，附所在文件，改动代码时照着抄不会出错。
2. **常用函数**——同版本下最常用但本项目暂时没用的 API，供后续扩展时参考。

> 版本以 `requirements.txt` 为准，括号内是当前虚拟环境实测安装版本。
> 想查完整 API：FastAPI 看 <https://fastapi.tiangolo.com/>，SQLAlchemy 看
> <https://docs.sqlalchemy.org/en/20/>，Pydantic 看 <https://docs.pydantic.dev/latest/>。

---

## 0. 依赖总览

| 库 | 版本要求（实测） | 作用 | 是否必需 |
|---|---|---|---|
| `fastapi` | >=0.100（0.165.0） | Web 框架、依赖注入、自动文档 | 必需 |
| `uvicorn[standard]` | >=0.20（0.54.0） | ASGI 服务器 | 必需 |
| `sqlalchemy` | >=2.0（2.1.9） | ORM、查询构造、连接池、事务 | 必需 |
| `pymysql` | >=1.1（1.2.4） | MySQL 驱动（纯 Python，免编译） | 必需 |
| `alembic` | >=1.12（1.20.1） | 数据库迁移 | 必需 |
| `pydantic` | v2（2.14.4） | 请求/响应模型与校验 | FastAPI 自带 |
| `pydantic-settings` | >=2.0（2.16.3） | 从 `.env` / 环境变量读取配置 | 必需 |
| `redis` | >=5.0（**当前未安装**） | 缓存与限流计数 | 可选 |
| `pytest` | >=7.4（9.2.0） | 测试框架 | 开发必需 |
| `httpx` | >=0.24（0.28.1） | `TestClient` 的底层 HTTP 客户端 | 开发必需 |
| `pyinstaller` | >=6.0（6.22.3） | 打包 exe | 打包时安装 |

`redis` 没装也能跑：`app/core/cache.py` 捕获 `ImportError` 后自动使用进程内内存缓存。
安装命令：`.\.venv\Scripts\python.exe -m pip install redis`。

### 使用分层原则（本项目约定）

| 层 | 允许直接用 | 不允许 |
|---|---|---|
| Controller | FastAPI（路由、依赖、Query/Path） | 直接 `select()` 查库 |
| Service | SQLAlchemy `Session`（事务、提交、回滚） | 处理 HTTP 状态码 |
| Repository | SQLAlchemy（`select`、`func`、`with_for_update`） | `db.commit()`（交给 Service） |
| Model | SQLAlchemy 类型与 `mapped_column` | 业务逻辑 |
| Schema | Pydantic 模型 | 访问数据库 |

---

## 1. FastAPI

### 1.1 本项目用到的

| API | 作用 | 位置 |
|---|---|---|
| `FastAPI(...)` | 创建应用，配置标题、文档地址 | `app/main.py` |
| `APIRouter(prefix=..., tags=...)` | 按模块拆分路由 | `app/controllers/*.py` |
| `@router.get/post/patch/delete(...)` | 定义接口，声明 `response_model`、`status_code`、`summary` | 各 Controller |
| `Depends()` | 依赖注入（数据库 Session、Service、登录校验、限流） | `app/dependencies.py`、`app/core/security.py` |
| `Query()` | 查询参数校验（`ge`、`le`、`default`、`description`） | 各 Controller |
| `Path()` | 路径参数校验 | 各 Controller |
| `Request` | 取请求头 / 客户端 IP（限流用） | `app/core/rate_limit.py` |
| `Response(status_code=204)` | 无响应体的删除接口 | `app/controllers/task_controller.py` |
| `StaticFiles(directory=...)` | 挂载 `/static` | `app/main.py` |
| `FileResponse` | 返回 `index.html` | `app/main.py` |
| `CORSMiddleware` | 跨域（前后端分离部署时用） | `app/main.py` |
| `JSONResponse` | 异常处理器返回统一 JSON | `app/core/exception_handlers.py` |

**应用入口**

```python
app = FastAPI(title="库存管理系统", version="2.0.0", ...)
app.add_middleware(CORSMiddleware, allow_origins=[...], allow_methods=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(order_router, prefix="/api")
```

**路由 + 依赖 + 参数校验**（`app/controllers/order_controller.py`）

```python
router = APIRouter(prefix="/orders", tags=["订单管理"])

@router.get(
    "",
    response_model=PageResponse[OrderOut],
    summary="订单列表",
    dependencies=[Depends(require_login)],
)
def list_orders(
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status: str | None = Query(default=None, description="订单状态"),
    service: OrderService = Depends(get_order_service),
):
    items, total = service.list_orders(status=status, page=page, size=size)
    return page_response(items, total, page, size)
```

**依赖链**：`Depends(get_order_service)` → `dependencies.py` 里再 `Depends(get_db)`，
每请求创建一个 Session，请求结束自动 `close()`。

**权限依赖**：`Depends(require_operator)` 返回当前用户，未登录抛 401、角色不够抛 403。
需要拿用户信息时用类型别名 `current_user: CurrentUser`。

**限流依赖**：`Depends(rate_limit(scope="order_create", limit=60, window_seconds=60))`。

**全局异常处理**

```python
@app.exception_handler(AppException)
async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )
```

### 1.2 常用 API（本项目未用到）

| API | 用途 | 说明 |
|---|---|---|
| `HTTPException(status_code, detail)` | 快速抛错 | 本项目统一用自定义异常 + 全局处理器，风格更统一 |
| `Body()`, `Header()`, `Cookie()`, `Form()` | 取请求体/头/Cookie/表单 | 上传文件用 `File()` |
| `UploadFile` / `File()` | 文件上传 | 需要 `python-multipart` |
| `BackgroundTasks` | 请求返回后执行任务（发邮件等） | 参数注入 `background_tasks: BackgroundTasks` |
| `@app.middleware("http")` | 自定义中间件 | 统一耗时日志、请求 ID |
| `@app.on_event("startup")` | 旧式启动钩子 | 本项目用 `lifespan` 上下文管理器 |
| `lifespan` | 新式启动/关闭钩子 | `app/main.py` 已使用 |
| `app.include_router(..., dependencies=[...])` | 路由级统一鉴权 | 避免每个接口重复写 `require_login` |
| `status.HTTP_201_CREATED` | 状态码常量 | 比裸数字可读 |
| `WebSocket` | 实时推送 | 订单看板可考虑 |

```python
from fastapi import BackgroundTasks, HTTPException, UploadFile, File, status

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile = File(...)):
    content = await file.read()
    return {"size": len(content)}
```

### 1.3 踩坑

- 路由匹配是**从上到下**的：`/orders/stats` 必须写在 `/orders/{order_id}` 前面，否则 `stats` 会被当成 ID。
- `response_model` 只做序列化，不会把 ORM 对象转成 dict，所以 `ConfigDict(from_attributes=True)` 必须写。
- `Depends()` 的缓存是**同一请求内**的：同一个依赖写两次只会执行一次。
- 挂载 `StaticFiles` 后，`/static/*` 优先于同名路由。

---

## 2. Pydantic v2

### 2.1 本项目用到的

| API | 作用 | 位置 |
|---|---|---|
| `BaseModel` | 所有请求/响应模型基类 | `app/schemas/*.py` |
| `ConfigDict(from_attributes=True)` | 允许从 ORM 对象序列化 | 所有 `*Out` 模型 |
| `Field(default, ge, max_length, description)` | 字段约束与文档 | 各 Schema |
| `computed_field` + `@property` | 计算字段（利润、单位成本） | `app/schemas/order.py` |
| `model_dump(mode="json")` | 转成可 JSON 序列化的 dict（Decimal → str） | `app/services/*_service.py` 写缓存前 |

```python
class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quantity: int = Field(ge=1, description="购买数量")
    unit_price: Decimal = Field(description="下单时单价快照")

    @computed_field(description="单位成本价")
    @property
    def unit_cost(self) -> Decimal | None:
        return self.product.cost if self.product else None
```

**嵌套模型 + 排除字段**：`product: ProductBrief | None = Field(default=None, exclude=True)`
表示这个关联对象只用来算成本，不输出到响应里。

**校验规则写在 Schema，不写在 Controller**：`quantity: int = Field(ge=1, le=9999)`，
超范围 FastAPI 直接返回 422，不需要手写判断。

### 2.2 常用 API（本项目未用到）

| API | 用途 |
|---|---|
| `field_validator` | 单字段自定义校验（如 SKU 转大写） |
| `model_validator(mode="after")` | 跨字段校验（如结束时间晚于开始时间） |
| `field_serializer` | 自定义字段输出格式（如日期只保留到天） |
| `SecretStr` | 密码/密钥避免被日志打印 |
| `TypeAdapter` | 脱离模型做类型校验（如校验 list[int]） |
| `ValidationError` | 捕获并自定义 422 响应 |
| `model_copy(update={...})` | 复制并改字段 |

```python
from pydantic import BaseModel, field_validator, model_validator

class TransferCreate(BaseModel):
    from_warehouse_id: int
    to_warehouse_id: int

    @field_validator("from_warehouse_id", "to_warehouse_id")
    @classmethod
    def positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("仓库 ID 必须为正数")
        return v

    @model_validator(mode="after")
    def not_same(self):
        if self.from_warehouse_id == self.to_warehouse_id:
            raise ValueError("调出和调入仓库不能相同")
        return self
```

### 2.3 踩坑

- v1 的 `class Config: orm_mode = True` 在 v2 失效，必须写 `model_config = ConfigDict(from_attributes=True)`。
- `Decimal` 在 JSON 里序列化为字符串（`"199.00"`），前端 `Number()` 后再计算。
- `model_dump()` 默认保留 `Decimal`，写缓存/转 JSON 要用 `mode="json"`。
- `computed_field` 必须放在 `@property` 上方，顺序反了不生效。

---

## 3. pydantic-settings

### 3.1 本项目用到的

```python
# app/core/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "mysql+pymysql://root:密码@localhost:3306/库存管理系统"
    cache_enabled: bool = False
    access_token_expire_minutes: int = 720

settings = Settings()
```

- 环境变量名与字段名大小写无关：`DATABASE_URL` → `database_url`。
- 优先级：**环境变量 > `.env` 文件 > 类里的默认值**。
- `settings` 是全局单例，测试里可以直接改属性（`tests/conftest.py` 就关掉了缓存和限流）。
- exe 运行时读的是**工作目录**下的 `.env`，`launcher.py` 会先 `os.chdir(exe 所在目录)`。

### 3.2 常用 API

| API | 用途 |
|---|---|
| `SettingsConfigDict(env_prefix="APP_")` | 统一加前缀，避免环境变量冲突 |
| `env_nested_delimiter="__"` | 嵌套配置（`DB__HOST`） |
| `SecretStr` | 密码字段，打印时显示 `**********` |
| `@field_validator` | 解析后二次校验/清洗 |
| `Settings(_env_file=".env.test")` | 测试环境换配置文件 |
| `model_config = SettingsConfigDict(extra="forbid")` | 拼错配置名时直接报错 |

### 3.3 踩坑

- `.env` 文件必须用 **UTF-8 无 BOM**，否则第一行 key 会带 `\ufeff` 读不到。
- 值里有 `#`、空格时建议加引号。
- 打包成 exe 后修改 `.env` 必须重启程序才生效（配置在导入时读取一次）。

---

## 4. SQLAlchemy 2.x

### 4.1 建模（本项目写法）

```python
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    product_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    category: Mapped["Category"] = relationship(back_populates="products", lazy="selectin")
```

| API | 作用 | 位置 |
|---|---|---|
| `DeclarativeBase` | 模型基类 | `app/db.py` |
| `Mapped[...]` + `mapped_column(...)` | 2.0 声明式类型注解写法 | `app/models/*.py` |
| `primary_key` / `nullable` / `unique` / `index` / `comment` | 列属性 | 各模型 |
| `ForeignKey("表.列")` | 外键 | 各模型 |
| `relationship(lazy="selectin")` | 关联加载策略（避免 N+1） | `app/models/order.py` |
| `Numeric(10, 2)` + `Decimal` | 金额精确计算 | 商品、订单 |
| `func.now()` / `func.count()` / `func.sum()` / `func.coalesce()` | SQL 函数 | 各 Repository |
| `server_default` / `default` | 数据库默认值 / Python 默认值 | 各模型 |

### 4.2 查询

| API | 作用 | 位置 |
|---|---|---|
| `select(Model)` | 构造 SELECT | 各 Repository |
| `.where(...)` / `.where(A, B)` | 条件（多条件 AND） | 各 Repository |
| `or_(a, b)` | OR 条件 | 商品/任务/用户模糊搜索 |
| `.order_by(Model.id.desc())` | 排序 | 列表接口 |
| `.offset((page-1)*size).limit(size)` | 分页 | 各 Repository |
| `select(func.count()).select_from(stmt.subquery())` | 统计总数（复用筛选条件） | 各 Repository |
| `select(func.sum(...), func.count(...))` | 一次查多个聚合值 | `order_repo.stats()` |
| `.join(Order, Order.id == OrderItem.order_id)` | 显式连接 | 订单统计 |
| `.with_for_update()` | 行锁（`SELECT ... FOR UPDATE`） | `product_repo.get_for_update` |
| `db.get(Model, pk)` | 按主键查询（走 identity map） | `get_by_id` |
| `db.scalar(stmt)` / `db.scalars(stmt).all()` | 取单值 / 取多行 | 各 Repository |
| `db.execute(stmt).one()` | 取一行多列（聚合结果） | `order_repo.stats()` |
| `func.coalesce(x, 0)` | NULL 转默认值 | 统计 |

```python
# 列表 + 总数（本项目标准写法）
base = select(Product).where(Product.product_name.like(f"%{keyword}%"))
total = db.scalar(select(func.count()).select_from(base.subquery()))
rows = list(db.scalars(base.order_by(Product.id.desc()).offset(0).limit(20)))

# 行锁：必须在事务里，否则锁立即释放
product = db.scalar(select(Product).where(Product.id == pid).with_for_update())
```

### 4.3 事务与并发

- `Session` 默认**不会自动提交**，Service 里显式 `db.commit()`；
- 出错时 `db.rollback()`，并把异常抛给 Controller；
- 多个商品按 `product_id` 升序依次加锁，降低死锁概率；
- `expire_on_commit=False`：提交后对象仍可读，避免响应序列化时再查一次库；
- `pool_pre_ping=True` + `pool_recycle=3600`：解决 MySQL 空闲 8 小时断连。

### 4.4 常用 API（本项目未用到）

| API | 用途 |
|---|---|
| `selectinload(Model.rel)` / `joinedload(...)` | 查询时预加载关联（替代 `lazy="selectin"`） |
| `db.add_all([...])` / `db.add(obj)` | 批量 / 单条新增 |
| `update(Model).where(...).values(...)` | 批量更新（一条 SQL） |
| `delete(Model).where(...)` | 批量删除 |
| `exists(...)` | 判断存在（比 count 快） |
| `case((条件, 值), else_=...)` | 类似 SQL CASE WHEN |（本项目任务排序用到）|
| `and_()` / `not_()` | 组合条件 |
| `db.begin()` / `with db.begin():` | 显式事务块 |
| `db.flush()` | 只发 SQL 不提交（拿自增 ID） |
| `db.refresh(obj)` | 重新从库读取 |
| `db.expire(obj)` | 标记对象过期，下次访问重查 |
| `Index` / `UniqueConstraint` | `__table_args__` 里声明复合索引/唯一约束 |
| `text("SELECT 1")` | 原生 SQL |

### 4.5 踩坑

- `Session` 不是线程安全的，多线程测试必须**每个线程一个 Session**（见 `tests/test_mysql_concurrency.py`）。
- 查询不提交也能读到数据（同一 Session），跨请求就看不到，别用全局 Session。
- `func.sum(Decimal)` 在 SQLite 下可能返回 `float`，要 `Decimal(str(v))` 兜底（`_to_money()`）。
- `with_for_update()` 在 SQLite 下**无效**，并发安全只能在 MySQL 验证。
- `lazy="selectin"` 只在**查询出对象时**生效，新建对象访问关联仍会触发单独查询。

---

## 5. PyMySQL

### 5.1 本项目用法

不直接调用，作为 SQLAlchemy 的驱动通过连接串使用：

```text
mysql+pymysql://root:密码@localhost:3306/库存管理系统?charset=utf8mb4
```

| 要素 | 说明 |
|---|---|
| `mysql+pymysql` | 方言 + 驱动 |
| `charset=utf8mb4` | 必须，中文与 emoji 都靠它 |
| 端口 3306 | MySQL 默认端口 |

### 5.2 常用 API（脚本里直接连库时）

```python
import pymysql

conn = pymysql.connect(
    host="127.0.0.1", port=3306, user="root", password="密码",
    database="库存管理系统", charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
)
with conn.cursor() as cur:
    cur.execute("SELECT id, product_name FROM products WHERE quantity < %s", (10,))
    rows = cur.fetchall()          # DictCursor 下是 list[dict]
conn.commit()                       # 写操作必须提交
conn.close()
```

| API | 作用 |
|---|---|
| `pymysql.connect(...)` | 建连接 |
| `conn.cursor()` / `DictCursor` | 游标 / 字典游标 |
| `cur.execute(sql, params)` | 参数化执行（**不要拼字符串**） |
| `cur.executemany(sql, seq)` | 批量写入 |
| `cur.fetchone()` / `fetchall()` | 取结果 |
| `cur.lastrowid` / `cur.rowcount` | 自增 ID / 影响行数 |
| `conn.begin()` / `commit()` / `rollback()` | 事务 |
| `pymysql.escape_string(s)` | 转义（能参数化就别用） |
| `pymysql.err.IntegrityError` | 唯一键/外键冲突 |

> 命令行导出中文库名在 Windows 上容易被 GBK 破坏，建议用 Navicat/Workbench 导出，
> 或用 Python（本项目就是这么备份的）。

---

## 6. Alembic

### 6.1 本项目用法

| API | 作用 | 位置 |
|---|---|---|
| `context.configure(...)` | 绑定 `target_metadata`、连接、`compare_type` | `migrations/env.py` |
| `op.create_table(...)` | 建表 | `migrations/versions/20261123_0001_initial_schema.py` |
| `op.drop_table(...)` | 回滚时删表 | 同上 |
| `sa.Column` / `sa.ForeignKeyConstraint` / `sa.Index` | 列、外键、索引定义 | 同上 |

```python
def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("product_name", sa.String(length=128), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

def downgrade() -> None:
    op.drop_table("products")
```

常用命令：

```powershell
.\.venv\Scripts\python.exe -m alembic current          # 当前版本
.\.venv\Scripts\python.exe -m alembic upgrade head     # 升级到最新
.\.venv\Scripts\python.exe -m alembic downgrade -1     # 回退一步
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "加字段"
.\.venv\Scripts\python.exe -m alembic upgrade head --sql > upgrade.sql
```

### 6.2 常用 API

| API | 用途 |
|---|---|
| `op.add_column("t", sa.Column(...))` | 加列 |
| `op.alter_column("t", "c", type_=..., nullable=..., server_default=...)` | 改列 |
| `op.drop_column("t", "c")` | 删列 |
| `op.create_index` / `op.drop_index` | 索引 |
| `op.execute("SQL")` | 执行原生 SQL（数据修正） |
| `op.bulk_insert(table, rows)` | 批量插初始数据 |
| `with op.batch_alter_table("t") as batch:` | SQLite 改表兼容写法 |

### 6.3 踩坑

- `alembic.ini` 尽量保持 ASCII：Windows 中文环境用 GBK 读配置会抛 `UnicodeDecodeError`。
- 用旧 SQL 脚本建的库不要直接 `upgrade head`，会重复建表；应执行 `upgrade_v2.sql` 后 `alembic stamp 0001`。
- `--autogenerate` 只对比模型与库，**不会**生成数据迁移。

---

## 7. Redis（可选）

未安装 `redis` 包或连不上服务时，`app/core/cache.py` 自动降级为进程内字典，业务无感。

### 7.1 本项目用到的

| API | 作用 | 位置 |
|---|---|---|
| `redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=0.3, socket_timeout=0.3)` | 建客户端（懒加载） | `cache._client()` |
| `client.ping()` | 探测可用性 | `cache._client()` |
| `client.get(key)` / `client.set(key, value, ex=ttl)` | 读写字符串 | `cache.get/set` |
| `client.delete(key)` | 删除单个 key | `cache.delete` |
| `client.scan_iter(match="前缀*")` | 按前缀批量删除（替代 `keys`，不阻塞） | `cache.delete_prefix` |
| `client.pipeline(transaction=True)` + `incr` + `expire` + `execute` | 原子自增 + 过期（限流） | `cache.incr` |

### 7.2 常用 API

| API | 用途 |
|---|---|
| `hset` / `hget` / `hgetall` / `hdel` | 哈希（存对象字段） |
| `lpush` / `rpop` / `lrange` | 列表（队列、最近记录） |
| `sadd` / `smembers` | 集合（去重统计） |
| `zadd` / `zrange` | 有序集合（排行榜） |
| `setex` / `expire` / `ttl` | 带过期的写 / 查剩余时间 |
| `incrby` / `decrby` | 增减计数 |
| `mset` / `mget` | 批量读写 |
| `publish` / `subscribe` | 消息广播 |
| `redis.exceptions.ConnectionError` | 连接异常（本项目用宽泛 catch 统一降级） |

### 7.3 踩坑

- `decode_responses=True` 后拿到的是 `str`，否则是 `bytes`。
- 生产环境（多进程/多机）必须用 Redis，内存缓存各进程互不相通。
- 缓存只是加速，**不能**作为唯一数据源；本项目任何写操作都会主动删 key。

---

## 8. Uvicorn

### 8.1 本项目用到的

```python
# launcher.py
uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
```

| API / 参数 | 作用 |
|---|---|
| `uvicorn.run(app, host, port)` | 启动 ASGI 服务 |
| `--reload` | 改代码自动重启（仅开发） |
| `--host 0.0.0.0` | 允许局域网其他机器访问 |
| `--proxy-headers` | 反向代理后取真实 IP（限流依赖它） |

### 8.2 常用参数

| 参数 | 说明 |
|---|---|
| `--workers 4` | 多进程（Windows 建议用 `--workers` 配合 `if __name__ == "__main__"`） |
| `--port 8001` | 端口被占用时换端口 |
| `--log-level debug` | 排查问题 |
| `uvicorn.Config` + `uvicorn.Server` | 代码里更细粒度控制 |

---

## 9. PyTest

### 9.1 本项目用到的

| API | 作用 | 位置 |
|---|---|---|
| `@pytest.fixture()` | 夹具：内存库、客户端、示例商品 | `tests/conftest.py` |
| `yield` 夹具 | 用例结束后的清理（关 Session、删表） | `tests/conftest.py` |
| `pytest.raises(异常)` | 断言抛错 | 各测试 |
| `pytest.mark.skipif(条件, reason=...)` | 没有 MySQL 时跳过并发用例 | `tests/test_mysql_concurrency.py` |
| `pytest.ini` 的 `testpaths` / `pythonpath` | 指定测试目录与导入根 | `pytest.ini` |
| `dependency_overrides` | 替换 `get_db`、`get_current_user`（属于 FastAPI，但只在测试里用） | `tests/conftest.py` |

```python
@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
```

### 9.2 常用 API

| API | 用途 |
|---|---|
| `@pytest.mark.parametrize("a,b", [...])` | 参数化用例 |
| `monkeypatch.setattr(obj, "attr", value)` | 临时替换依赖/配置 |
| `tmp_path` | 临时目录（导出文件测试） |
| `capsys` | 捕获 print 输出 |
| `pytest.approx(1.0)` | 浮点近似比较 |
| `pytest.skip("原因")` | 运行时跳过 |
| `@pytest.fixture(scope="session")` | 整个测试会话共享（如引擎） |
| `pytest -k 关键字` / `-x` / `-vv` | 筛选用例 / 首个失败即停 / 详细输出 |

### 9.3 踩坑

- 内存 SQLite 要配 `StaticPool` + `check_same_thread=False`，否则多个连接看不到同一份数据。
- 夹具之间可以互相依赖（`client` 依赖 `db_session` 和 `admin_user`）。
- 测试里改 `settings` 是全局生效的，注意别污染其他用例（`conftest.py` 里统一设置）。

---

## 10. HTTPX + TestClient

### 10.1 本项目用到的

```python
from fastapi.testclient import TestClient

with TestClient(app) as client:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    resp = client.get("/api/orders", headers={"Authorization": f"Bearer {token}"})
```

| API | 作用 |
|---|---|
| `TestClient(app)` | 起一个内存里的服务，不占端口 |
| `client.get/post/patch/delete(url, json=..., headers=...)` | 发请求 |
| `resp.status_code` / `resp.json()` / `resp.text` | 断言用 |
| `app.dependency_overrides[get_db] = ...` | 替换依赖（换测试库、跳过登录） |

### 10.2 常用（httpx 直接调用外部接口）

| API | 用途 |
|---|---|
| `httpx.get(url, params=..., timeout=...)` | 同步请求 |
| `httpx.Client(base_url=..., headers=...)` | 复用连接 |
| `httpx.AsyncClient` | 异步请求 |
| `resp.raise_for_status()` | 4xx/5xx 抛异常 |

> `TestClient` 依赖 `httpx`，所以 `requirements.txt` 里必须装它，否则测试跑不起来。

---

## 11. PyInstaller

### 11.1 本项目用法

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --console `
  --name InventoryManager --collect-all uvicorn --collect-all fastapi `
  --collect-all sqlalchemy --hidden-import pymysql --hidden-import greenlet `
  --add-data "app/static;app/static" launcher.py
```

| 参数 | 作用 |
|---|---|
| `--onefile` | 打成单个 exe（启动时解压到临时目录，稍慢） |
| `--console` | 保留黑窗口看日志（`--windowed` 会隐藏） |
| `--add-data "源;目标"` | 把前端静态文件打进去（Windows 用分号） |
| `--collect-all 包` | 收集包的全部子模块与数据文件（uvicorn/fastapi 必需） |
| `--hidden-import` | 显式声明动态导入的模块（pymysql、greenlet） |
| `--clean` | 清理缓存后重新构建 |

### 11.2 踩坑

- `greenlet` 是 SQLAlchemy 异步/并发的依赖，漏了会在运行时 `ModuleNotFoundError`。
- 静态文件路径要用 `sys._MEIPASS`/`__file__` 定位，本项目还额外支持“exe 同目录 `static` 优先”。
- 杀毒软件可能误报 onefile 包，需要加白名单。
- 每次改 Python 代码都要重新打包；只改前端只需覆盖 `dist\static`。

---

## 12. 标准库中的关键工具

| 模块 | 本项目用途 | 位置 |
|---|---|---|
| `hashlib.pbkdf2_hmac("sha256", pwd, salt, iterations)` | 密码哈希 | `app/core/security.py` |
| `hmac.new(...)` / `hmac.compare_digest(...)` | JWT 签名 / 常量时间比较 | `app/core/security.py` |
| `base64.urlsafe_b64encode/b64decode` | JWT 的 Base64URL 编码 | `app/core/security.py` |
| `secrets.token_bytes(16)` | 生成盐 | `app/core/security.py` |
| `time.time()` | token 过期时间戳 | `app/core/security.py` |
| `threading.Lock` | 内存缓存与 Redis 懒加载的线程安全 | `app/core/cache.py` |
| `collections.abc.Generator` | 依赖注入生成器类型 | `app/db.py` |
| `decimal.Decimal` | 金额精确计算 | 订单、商品 |
| `uuid.uuid4().hex` | 订单号/退货单号后缀 | `app/services/order_service.py` |
| `datetime.now()` | 支付/取消时间 | 订单服务 |
| `pathlib.Path` | 静态文件路径拼接 | `app/main.py` |
| `logging` | 统一日志（不用 print） | 全局 |

---

## 13. 速查：本项目最常写的 15 段代码

```python
# 1. 新接口（带权限）
@router.get("", response_model=PageResponse[FooOut], dependencies=[Depends(require_login)])
def list_foo(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
             service: FooService = Depends(get_foo_service)):
    items, total = service.list(page=page, size=size)
    return page_response(items, total, page, size)

# 2. 从 ORM 对象取字段
class FooOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str

# 3. 分页查询
stmt = select(Foo).where(Foo.name.like(f"%{kw}%"))
total = db.scalar(select(func.count()).select_from(stmt.subquery()))
items = list(db.scalars(stmt.order_by(Foo.id.desc()).offset((p-1)*s).limit(s)))

# 4. 行锁 + 校验
product = db.scalar(select(Product).where(Product.id == pid).with_for_update())
if product is None:
    raise NotFoundError("商品不存在")
if product.quantity < qty:
    raise InsufficientStockError("库存不足")

# 5. 事务提交与回滚
try:
    db.commit()
except Exception:
    db.rollback()
    raise

# 6. 写缓存
cache.set_json(CACHE_KEY, data.model_dump(mode="json"))

# 7. 读缓存
cached = cache.get_json(CACHE_KEY)
if cached is not None:
    return Stats(**cached)

# 8. 失效缓存
cache.delete(CACHE_KEY_PRODUCT_STATS, CACHE_KEY_ORDER_STATS)

# 9. 业务异常
raise ConflictError("订单已经支付，请勿重复支付")

# 10. 密码哈希与校验
hashed = hash_password("admin123")
ok = verify_password("admin123", hashed)

# 11. 签发 token
token, expires_in = create_access_token(user_id=1, username="admin", role="admin")

# 12. 依赖注入 Service
def get_order_service(db: Session = Depends(get_db)) -> OrderService:
    return OrderService(db)

# 13. 测试请求
resp = client.post("/api/orders", json={"items": [{"product_id": 1, "quantity": 2}]})

# 14. 前端调用接口（app.js）
const data = await api("/api/orders", { method: "POST", body: JSON.stringify(payload) });

# 15. 前端分页器（含页码直达）
bindPager("order", "orders", loadOrders);
renderPagerCore("order", "orders", "单");
buildPagerItems(5, 30);   // → [1, "…", 3, 4, 5, 6, 7, "…", 30]
```
