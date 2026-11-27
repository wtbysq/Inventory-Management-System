# 架构与代码说明

本文档说明项目的分层设计、请求流程、库存事务、异常处理和测试策略。

---

## 1. 分层架构

```text
┌──────────────────────────────────────┐
│            Controller                │
│  接收 HTTP 请求、参数校验、返回响应       │
└──────────────────┬───────────────────┘
                   │ 调用
┌──────────────────▼───────────────────┐
│              Service                 │
│  业务规则、事务控制、业务异常             │
└──────────────────┬───────────────────┘
                   │ 调用
┌──────────────────▼───────────────────┐
│             Repository               │
│  SQL 查询、分页、聚合、持久化            │
└──────────────────┬───────────────────┘
                   │ SQLAlchemy
┌──────────────────▼───────────────────┐
│               MySQL                  │
│  categories / products / inventory_logs │
└──────────────────────────────────────┘
```

依赖方向是单向的：

```text
Controller -> Service -> Repository -> Model -> MySQL
```

不允许：

- Controller 直接写 SQL
- Service 直接处理 HTTP 状态码
- Repository 做业务判断
- Model 里写业务流程

---

## 2. 请求生命周期

### 2.1 查询商品列表

```text
GET /api/products?keyword=T恤&page=1&size=20
        ↓
ProductController.list_products
        ↓
ProductService.list_products
        ↓
ProductRepository.search
        ↓
SELECT ... WHERE product_name LIKE '%T恤%' LIMIT 20 OFFSET 0
        ↓
FastAPI 根据 PageResponse[ProductOut] 序列化响应
```

### 2.2 商品出库

```text
POST /api/inventory/outbound
        ↓
InventoryController.outbound
        ↓
InventoryService.outbound
        ↓
InventoryService._change_stock
        ↓
开启数据库事务
        ↓
ProductRepository.get_for_update
        ↓
SELECT * FROM products WHERE id = ? FOR UPDATE
        ↓
检查库存是否足够
        ↓
更新 products.quantity
        ↓
写入 inventory_logs
        ↓
commit 提交事务
```

如果库存不足，Service 抛出 `InsufficientStockError`，
事务回滚，商品库存和流水都不会变化。

### 2.3 创建订单

```text
POST /api/orders
        ↓
OrderController.create_order
        ↓
OrderService.create_order
        ↓
合并同一商品的多行数量
        ↓
创建订单主记录并 flush
        ↓
按 product_id 排序
        ↓
逐个 SELECT ... FOR UPDATE 锁定商品
        ↓
校验库存
        ↓
扣减 products.quantity
        ↓
写入 order_items
        ↓
写入 inventory_logs（OUT）
        ↓
计算 total_amount
        ↓
commit
```

任意商品库存不足时，整个订单事务回滚。

---

## 3. 各层职责

| 层 | 目录 | 职责 | 不应该做什么 |
|---|---|---|---|
| Controller | `app/controllers/` | 接收请求、读取查询参数、调用 Service、返回响应 | 不写业务规则，不直接操作数据库 |
| Service | `app/services/` | 业务判断、事务边界、抛业务异常 | 不关心 HTTP 状态码，不直接拼 SQL |
| Repository | `app/repositories/` | 数据查询、分页、聚合、持久化 | 不做库存是否足够的业务判断 |
| Model | `app/models/` | 映射数据库表、定义字段和关系 | 不写业务流程 |
| Schema | `app/schemas/` | 定义请求体和响应体、参数校验 | 不查数据库 |
| Core | `app/core/` | 公共异常、异常处理器 | 不包含具体业务模块逻辑 |

---

## 4. 文件职责详解

### 4.1 应用入口与基础设施

| 文件 | 说明 |
|---|---|
| `app/main.py` | 创建 FastAPI 实例，注册 CORS、路由、全局异常处理器、健康检查 |
| `app/db.py` | 读取配置、创建 `engine`、`SessionLocal`、ORM 基类 `Base`、提供 `get_db()` |
| `app/dependencies.py` | 把数据库 Session 注入 Service，供 Controller 通过 `Depends` 使用 |

`db.py` 中：

- `Settings` 从环境变量或 `.env` 读取 `DATABASE_URL`、`DB_ECHO`
- `engine` 使用 `pool_pre_ping=True`，避免 MySQL 长连接断开
- `SessionLocal` 设置 `expire_on_commit=False`，提交后仍可读取 ORM 对象属性
- `get_db()` 使用 `yield`，请求结束后自动 `close()`

### 4.2 模型层

| 文件 | 说明 |
|---|---|
| `app/models/types.py` | 定义 `BIGINT_ID`、`BIGINT_UNSIGNED_ID`，MySQL 使用 BIGINT，SQLite 测试自动降级为 INTEGER |
| `app/models/category.py` | `Category` 模型，对应 `categories` 表 |
| `app/models/product.py` | `Product` 模型，对应 `products` 表，包含分类关系和库存流水关系 |
| `app/models/inventory_log.py` | `InventoryLog` 模型，对应 `inventory_logs` 表 |
| `app/models/order.py` | `Order`、`OrderItem` 模型，对应 `orders`、`order_items` 表 |
| `app/models/__init__.py` | 统一导入所有模型，保证 `Base.metadata` 包含全部表 |

`Product` 关键字段：

- `quantity`：当前库存
- `price`：销售价
- `cost`：成本价，用于统计库存总价值
- `low_stock_threshold`：低库存阈值
- `last_inbound_at` / `last_outbound_at`：最近一次出入库时间

### 4.3 Schema 层

| 文件 | 说明 |
|---|---|
| `app/schemas/common.py` | `PageResponse[T]`、`page_response()`，统一分页响应 |
| `app/schemas/category.py` | `CategoryOut` |
| `app/schemas/product.py` | `ProductOut`、`ProductStats` |
| `app/schemas/inventory.py` | `InventoryChangeRequest`、`InventoryLogOut` |
| `app/schemas/order.py` | `OrderCreate`、`OrderItemCreate`、`OrderOut`、`OrderItemOut`、`OrderStats` |

Schema 使用 Pydantic：

- 自动校验 `quantity > 0`
- 自动校验 `page >= 1`、`size <= 100`
- 自动校验订单至少包含一个商品
- Swagger 文档中自动展示字段类型、说明和示例

### 4.4 Repository 层

| 文件 | 说明 |
|---|---|
| `app/repositories/category_repo.py` | 查询全部分类、按 ID 查询分类 |
| `app/repositories/product_repo.py` | 商品分页、模糊搜索、分类筛选、低库存、库存统计、行锁查询 |
| `app/repositories/inventory_log_repo.py` | 新增流水、按商品分页查询流水 |
| `app/repositories/order_repo.py` | 新增订单、订单详情、订单分页、状态筛选、订单号搜索 |

`ProductRepository.search()` 同时支持：

```text
keyword + category_id + low_stock_only + page + size
```

统计查询：

```sql
-- 商品种类数
SELECT COUNT(id) FROM products;

-- 库存总数量
SELECT SUM(quantity) FROM products;

-- 库存总价值
SELECT SUM(quantity * COALESCE(cost, 0)) FROM products;

-- 低库存数量
SELECT COUNT(id) FROM products
WHERE quantity < low_stock_threshold;
```

### 4.5 Service 层

| 文件 | 说明 |
|---|---|
| `app/services/category_service.py` | 分类查询业务 |
| `app/services/product_service.py` | 商品列表、详情、低库存、库存统计 |
| `app/services/inventory_service.py` | 入库、出库、事务、库存校验、流水写入 |
| `app/services/order_service.py` | 创建订单、合并重复商品、批量扣库存、整单事务回滚 |

`InventoryService` 和 `OrderService` 是核心业务类。

### 4.6 Controller 层

| 文件 | 说明 |
|---|---|
| `app/controllers/category_controller.py` | `GET /api/categories` |
| `app/controllers/product_controller.py` | 商品列表、统计、低库存、详情 |
| `app/controllers/inventory_controller.py` | 入库、出库、流水查询 |
| `app/controllers/order_controller.py` | 创建订单、订单列表、订单详情 |

Controller 保持轻薄，只做三件事：

1. 接收参数
2. 调用 Service
3. 返回结果

### 4.7 Core 层

| 文件 | 说明 |
|---|---|
| `app/core/exceptions.py` | `AppException`、`NotFoundError`、`InsufficientStockError`、`ValidationError` |
| `app/core/exception_handlers.py` | 把业务异常转换为统一 JSON |

### 4.8 前端页面

| 文件 | 说明 |
|---|---|
| `app/static/index.html` | 管理页面结构：统计卡片、商品表格、出入库弹窗、订单弹窗 |
| `app/static/styles.css` | 页面样式和响应式布局 |
| `app/static/app.js` | 调用后端 API，渲染商品列表，处理搜索、分页、出入库和下单交互 |

页面入口：

```text
GET /
```

静态资源：

```text
/static/styles.css
/static/app.js
```

`app/main.py` 使用 `FileResponse` 返回 `index.html`，并通过 `StaticFiles` 挂载 `/static`。

PyInstaller 打包时通过：

```powershell
--add-data "app/static;app/static"
```

把前端文件一起打进 exe。

---

## 5. 库存事务与并发

### 5.1 事务边界

`InventoryService._change_stock()` 中：

```python
try:
    product = self.product_repo.get_for_update(product_id)
    ...
    self.db.add(log)
    self.db.commit()
    return log
except Exception:
    self.db.rollback()
    raise
```

库存变更和流水写入在同一个事务中：

- 成功：商品库存更新 + 流水新增 同时提交
- 失败：两者全部回滚

这样可以避免：

- 库存扣了，但流水没写
- 流水写了，但库存没扣

### 5.2 防止超卖

`ProductRepository.get_for_update()` 使用：

```sql
SELECT * FROM products WHERE id = ? FOR UPDATE
```

MySQL InnoDB 会对该商品行加排他锁。

两个请求同时出库时：

```text
请求 A 先拿到行锁
请求 B 等待
A 扣减库存并提交
B 拿到锁后重新读取库存
B 发现库存不足，返回 409
```

注意：

- MySQL 表必须使用 `InnoDB`
- 行锁必须在事务中生效
- SQLite 不支持真正的 `FOR UPDATE`，所以 SQLite 测试不能完全验证并发安全

### 5.3 库存不能为负

有两层保护：

1. Service 层判断 `before_quantity < quantity`
2. 数据库层 `CHECK (quantity >= 0)`

### 5.4 下单事务

`OrderService.create_order()` 的流程：

```text
合并同一商品的多行数量
        ↓
创建 orders 主记录并 flush 获取订单 ID
        ↓
按 product_id 排序
        ↓
逐个 SELECT ... FOR UPDATE 锁定商品
        ↓
校验库存
        ↓
扣减 products.quantity
        ↓
写入 order_items
        ↓
写入 inventory_logs（OUT）
        ↓
计算订单总金额
        ↓
commit
```

关键设计：

- **同一商品多行合并**：避免对同一商品重复加锁和重复扣减。
- **按商品 ID 排序加锁**：降低两个订单交叉锁定商品造成死锁的概率。
- **整单事务**：任意商品库存不足，订单、明细、库存、流水全部回滚。
- **商品快照**：`order_items` 保存商品名称、SKU、单价，历史订单不受商品改价影响。
- **出库流水**：每个订单商品都会写入一条 `inventory_logs`，备注包含订单号。

---

## 6. 异常处理

业务异常继承 `AppException`：

| 异常 | HTTP 状态码 | 错误码 |
|---|---:|---|
| `NotFoundError` | 404 | `NOT_FOUND` |
| `InsufficientStockError` | 409 | `INSUFFICIENT_STOCK` |
| `ValidationError` | 422 | `VALIDATION_ERROR` |

统一响应格式：

```json
{
  "code": "INSUFFICIENT_STOCK",
  "message": "商品 FZ-0001 库存不足，当前库存 2，需要 5"
}
```

Service 只负责抛业务异常，不关心 HTTP；由 `exception_handlers.py` 统一转换。

---

## 7. 测试策略

### 7.1 单元测试

`tests/test_inventory_service.py` 直接测试 Service：

- 入库后库存增加
- 入库生成 `IN` 流水
- 出库后库存减少
- 出库生成 `OUT` 流水
- 库存不足抛异常
- 库存不足时库存不变、流水不生成
- 数量为 0 时拒绝入库

`tests/test_order_service.py` 测试订单 Service：

- 下单后扣减库存
- 生成订单明细和出库流水
- 同一商品重复行合并
- 多商品订单金额和库存
- 库存不足时整单回滚
- 订单列表返回明细

### 7.2 接口测试

`tests/test_api.py` 使用 FastAPI `TestClient`：

- `/health`
- `/api/categories`
- `/api/products`
- `/api/products/stats`
- `/api/inventory/inbound`
- `/api/inventory/outbound`
- `/api/orders`
- `/api/orders/{order_id}`
- `/` 管理页面
- `/static/styles.css`、`/static/app.js`
- 库存不足返回 409

### 7.3 测试数据库

测试使用 SQLite 内存数据库：

```text
sqlite+pysqlite:///:memory:
```

通过 `StaticPool` 让多个连接共享同一个内存库。

优点：

- 启动快
- 不依赖本地 MySQL
- 每次测试独立

局限：

- 不能验证 MySQL 行锁
- 不能验证 MySQL `CHECK` 约束
- SQL 方言与 MySQL 不完全一致

建议后续增加真实 MySQL 集成测试，重点验证并发出库。

---

## 8. 设计取舍

### 为什么 Controller 不直接查数据库？

为了让业务逻辑可测试、可复用。直接写 SQL 会导致：

- 路由函数越来越长
- 业务规则分散
- 无法脱离 HTTP 测试业务逻辑

### 为什么库存流水单独建表？

商品表只保存“当前库存”和“最近出入库时间”，
流水表保存每一次变化。

这样既可以快速展示当前库存，又可以追溯历史。

### 为什么统计放在 Repository？

因为统计本质上是数据库聚合查询：

```sql
SUM(quantity * cost)
```

放在 Repository 可以避免把 SQL 散落到 Service 或 Controller。

---

## 9. v2 新增模块设计

### 9.1 认证与权限链路

```text
请求头 Authorization: Bearer <token>
        ↓
get_current_user（依赖）
        ↓ 解析 JWT、查 users 表、校验 is_active
require_roles("admin", "operator")（依赖工厂）
        ↓ 角色不匹配抛 ForbiddenError(403)
Controller 业务函数
```

关键实现：

- `app/core/security.py`
  - `hash_password` / `verify_password`：PBKDF2-SHA256 + 随机盐，
    存储格式 `pbkdf2_sha256$迭代次数$盐$哈希`；
  - `create_access_token` / `decode_access_token`：手写 HS256 JWT，
    只使用标准库 `hmac`、`hashlib`、`base64`、`json`；
  - `require_roles` 返回一个 FastAPI 依赖，Controller 用
    `dependencies=[Depends(require_operator)]` 声明即可。
- `app/services/auth_service.py`
  - 登录失败统一提示“用户名或密码错误”，不暴露账号是否存在；
  - 修改/禁用管理员前检查启用管理员数量，避免系统失去管理员；
  - `bootstrap_default_admin` 在 `lifespan` 中调用，用户表为空时才创建。

为什么不在每个 Controller 里写 `if user.role != ...`？
因为权限判断属于横切关注点，用依赖声明可以避免遗漏，
也方便测试时通过 `app.dependency_overrides` 替换当前用户。

### 9.2 订单状态机

```text
CREATED --pay--> PAID --return--> PARTIALLY_RETURNED --return--> RETURNED
   |
   +--cancel--> CANCELLED
```

约束：

- `pay`：仅 `CREATED` 可支付，重复支付返回 409；
- `cancel`：仅 `CREATED` 可取消，已支付订单必须走退货；
- `return`：仅 `PAID` / `PARTIALLY_RETURNED` 可退货，
  每次退货写入 `order_returns` 与 `order_return_items`，
  并在 `order_items.returned_quantity` 上累加。

所有状态变更都先 `SELECT ... FOR UPDATE` 锁定订单行，
防止两个请求同时支付或重复退货。

### 9.3 退货为什么单独建表

如果只在订单上记一个 `refunded_amount`：

- 无法知道每次退了哪些商品、退了几件；
- 无法支持部分退货和多次退货；
- 无法追溯退货原因和经办人。

因此采用：

```text
orders 1 ── n order_returns 1 ── n order_return_items
order_items 1 ── n order_return_items
```

订单只保存汇总（`refunded_amount`），明细在退货单里。
退货金额使用订单明细的 `unit_price` 快照，商品后续改价不影响退款。

### 9.4 仓库库存与总库存一致性

引入仓库后有两个库存口径：

```text
products.quantity          总库存（页面展示、下单校验）
warehouse_stocks.quantity  某仓库库存（调拨使用）
```

约束：`products.quantity == Σ warehouse_stocks.quantity`

初始化规则（`WarehouseRepository.ensure_stock`）：

- 商品没有任何仓库记录 → 默认仓库 = 总库存；
- 商品在其他仓库已有库存 → 默认仓库 = 总库存 - 其他仓库之和；
- 非默认仓库第一次出现 → 0，需要先调拨进来。

因此老库（只有 `products.quantity`）不需要手工补数据，
第一次涉及该商品的业务会自动补齐默认仓库库存。
`sql/upgrade_v2.sql` 也会批量初始化一次，减少首次访问的写操作。

同步策略：

| 操作 | 默认仓库 | 总库存 |
|---|---|---|
| 入库 | +N | +N |
| 出库 | -N（不足则拒绝） | -N |
| 下单 | -N（不足则拒绝） | -N |
| 取消/退货 | +N | +N |
| 调拨 | 调出 -N / 调入 +N | 不变 |
| 盘盈 | +N | +N |
| 盘亏 | 先扣默认仓库，再扣其他仓库 | -N |

调用顺序很重要：`apply_default_delta` / `apply_total_delta` 必须在
修改 `product.quantity` **之前**调用，因为初始化默认仓库库存时需要
读取变动前的总库存。

### 9.5 盘点

盘点单保存创建时的账面快照：

```text
stocktake_items.expected_quantity  创建时的 products.quantity
stocktake_items.counted_quantity   人工录入
stocktake_items.difference         实盘 - 账面
```

确认盘点时：

1. 锁定盘点单，状态必须是 `COUNTING`；
2. 按 `product_id` 排序逐个锁定商品；
3. 用实盘数量覆盖 `products.quantity`；
4. 差异同步到仓库库存（盘亏会跨仓库扣减）；
5. 写 `ADJUST` 流水（记录 before / after）；
6. 盘点单状态改为 `CONFIRMED`。

未录入实盘数量的商品会被跳过，支持只盘部分商品。

### 9.6 调拨

调拨单创建即完成（`COMPLETED`），因为业务上仓库间移动不需要审批。

```text
锁定商品行
  → ensure_stock(调出仓)
  → ensure_stock(调入仓)
  → 校验调出仓库存
  → 调出 -N、调入 +N
  → 写调拨明细
```

不做的事情：不写 `inventory_logs`。因为流水的 `before_quantity` /
`after_quantity` 描述的是总库存，而调拨前后总库存不变，
写进去反而会让流水难以理解。仓库维度的变化由调拨单明细完整记录。

### 9.7 缓存

```text
GET /api/products/stats        GET /api/orders/stats
        ↓                              ↓
cache.get_json(...) ──命中──▶ 直接返回
        ↓ 未命中
Repository 聚合查询
        ↓
cache.set_json(..., TTL=30s)
```

两个统计接口都走同一套模式，key 分别是 `products:stats` 与 `orders:stats`：

| 缓存 | 失效时机 |
|---|---|
| 商品统计 | 出入库、下单、取消、退货、盘点、调拨成功后 |
| 订单经营统计 | 支付、取消、退货成功后（订单创建不影响已支付统计） |

失效使用 `cache.delete(...)`（支持一次传多个 key），
刷新首页看板时最多只触发一次数据库聚合。

`app/core/cache.py` 的策略：

- 懒连接 Redis（首次使用时 ping，超时 0.3s）；
- 连接失败标记不可用，全部操作走内存字典；
- 内存实现带线程锁和过期时间，支持 `incr`；
- 限流计数不受 `CACHE_ENABLED` 影响，因为它是安全能力而不是性能优化。

### 9.8 限流

固定窗口算法：

```text
key = inventory:rl:{scope}:{ip}
count = INCR key
EXPIRE key window（第一次时设置）
count > limit → 429 RATE_LIMITED
```

作为 FastAPI 依赖挂在接口上：

```python
@router.post(
    "",
    dependencies=[
        Depends(require_operator),
        Depends(rate_limit(scope="order_create", limit=60)),
    ],
)
```

依赖执行顺序在业务函数之前，因此超限请求不会进入 Service，
也不会占用数据库连接。

### 9.9 Alembic 迁移

- `alembic.ini` 不写数据库密码；
- `migrations/env.py` 从 `settings.database_url` 读取，并导入
  `app.models` 注册全部表；
- `0001_initial_schema` 创建 15 张表并插入默认仓库；
- 旧库走 `sql/upgrade_v2.sql` + `alembic stamp 0001`。

`alembic.ini` 使用 ASCII 注释是刻意为之：Alembic 用系统 locale
读取 ini 文件，中文 Windows 的 GBK 会直接解析失败。

### 9.10 真实并发测试

单元测试使用 SQLite，`with_for_update()` 不会真正加行锁，
因此只能验证业务逻辑，不能验证并发安全。

真实测试（`tests/test_mysql_concurrency.py`、
`scripts/mysql_concurrency_test.py`）：

```text
库存 10
20 个线程同时下单，每单 1 件
    ↓
行锁串行化：前 10 个事务成功，后 10 个读到库存 0 抛 InsufficientStockError
    ↓
断言：成功 10、失败 10、最终库存 0、订单 10、出库流水 10
```

测试数据准备阶段会提前创建默认仓库和仓库库存，
避免并发时多个事务同时插入同一条 `warehouse_stocks` 触发唯一约束。

---

## 10. 后续扩展建议

1. **订单超时自动取消**：定时任务扫描 `CREATED` 超过 30 分钟的订单并回补库存。
2. **真实支付**：接入支付网关，回调确认后再把订单改为 `PAID`。
3. **退货审批**：退货单增加 `PENDING_APPROVAL` 状态，审批通过才回补库存。
4. **库位管理**：仓库下再分层 `zone / shelf / bin`。
5. **审计日志**：记录每次写操作的 before / after，便于追责。
6. **异步化**：流水写入、通知发送走消息队列。
7. **前端工程化**：独立 Vue / React 项目或小程序，复用现有 REST API。
