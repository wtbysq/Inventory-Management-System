# 库存管理系统

基于 **FastAPI + SQLAlchemy 2.x + MySQL 8 + Redis（可选）** 的进销存系统，
采用 `Controller → Service → Repository → Model` 四层架构，
自带中文管理页面，可打包成单个 exe 分发。

- 后端：FastAPI，自动生成 Swagger / ReDoc
- 前端：原生 HTML + CSS + JS，无需 Node、无需构建
- 数据库：MySQL 8（InnoDB），Alembic 管理迁移
- 测试：PyTest，48 个用例通过 + 1 个真实 MySQL 并发用例（默认跳过）

项目按用途分成两个目录，互不混杂：

```text
库存管理系统/
├── 源码/          ← 当前目录：Python 源码、测试、迁移脚本、文档
└── 移植文件/      ← exe + static + sql，拷到别的电脑就能建库运行
```

---

## 目录

- [1. 功能特性](#1-功能特性)
- [2. 技术栈](#2-技术栈)
- [3. 项目结构](#3-项目结构)
- [4. 快速开始](#4-快速开始)
- [5. 角色与权限](#5-角色与权限)
- [6. 核心业务规则](#6-核心业务规则)
- [7. API 清单](#7-api-清单)
- [8. 数据模型](#8-数据模型)
- [9. 缓存与限流](#9-缓存与限流)
- [10. 数据库迁移](#10-数据库迁移)
- [11. 前端使用说明](#11-前端使用说明)
- [12. 运行测试](#12-运行测试)
- [13. 打包成 exe](#13-打包成-exe)
- [14. 换电脑 / 局域网部署](#14-换电脑--局域网部署)
- [15. 常见问题](#15-常见问题)
- [16. 开发约定](#16-开发约定)
- [17. 文档](#17-文档)

---

## 1. 功能特性

| 模块 | 能力 |
|---|---|
| 商品与库存 | 分页搜索（名称 / SKU）、分类筛选、低库存预警、库存总览、出入库流水、**订单弹窗内商品实时搜索** |
| 订单 | 下单扣库存、支付、取消（回补库存）、部分 / 全部退货、退款记录、**订单利润与累计利润看板** |
| 任务管理 | 任务 CRUD、状态流转、优先级排序、按状态统计 |
| 库存盘点 | 创建盘点单（账面快照）、录入实盘、确认后自动调差并写流水 |
| 仓库调拨 | 多仓库库存、仓库间调拨、调拨单审计 |
| 用户与权限 | 登录、JWT、PBKDF2 密码哈希、RBAC（管理员 / 操作员 / 只读） |
| 缓存与限流 | Redis 缓存统计接口、接口限流、Redis 不可用时自动降级 |
| 数据库迁移 | Alembic 迁移 + 旧库增量升级 SQL |
| 并发验证 | 真实 MySQL 多线程并发下单测试（验证行锁不超卖） |
| 分发 | PyInstaller 单文件 exe，前端支持热替换 |

---

## 2. 技术栈

| 技术 | 版本要求 | 作用 |
|---|---|---|
| Python | 3.11+（实测 3.13） | 运行环境 |
| FastAPI | >=0.100 | Web API 框架、依赖注入、自动文档 |
| Uvicorn | >=0.20 | ASGI 服务器 |
| SQLAlchemy | >=2.0 | ORM、查询构造、连接池 |
| PyMySQL | >=1.1 | MySQL 驱动（纯 Python，免编译） |
| MySQL | 8.x | 业务数据存储，InnoDB 行锁保证并发安全 |
| Pydantic | v2 | 请求校验、响应序列化 |
| pydantic-settings | >=2.0 | 从 `.env` / 环境变量读取配置 |
| Alembic | >=1.12 | 数据库迁移 |
| Redis | >=5.0（可选） | 统计缓存、限流计数 |
| PyTest + HTTPX | >=7.4 / >=0.24 | 单元测试与接口测试 |
| PyInstaller | >=6.0 | 打包 exe |

登录凭证使用标准库实现的 **JWT（HS256）**，密码使用 **PBKDF2-SHA256**，
不依赖 PyJWT / bcrypt，减少部署依赖。各库的详细函数用法见
[docs/LIBRARIES.md](docs/LIBRARIES.md)。

---

## 3. 项目结构

```text
库存管理系统/
├── app/
│   ├── main.py                 # 应用入口：中间件、路由、静态文件、启动初始化
│   ├── db.py                   # 引擎、Session 工厂、Base、get_db
│   ├── dependencies.py         # 各 Service 的依赖注入
│   ├── core/
│   │   ├── config.py           # 集中配置（数据库 / 安全 / 缓存 / 限流）
│   │   ├── security.py         # PBKDF2、JWT、当前用户、角色依赖
│   │   ├── cache.py            # Redis + 内存降级缓存
│   │   ├── rate_limit.py       # 固定窗口限流依赖
│   │   ├── exceptions.py       # 业务异常（401/403/404/409/422/429）
│   │   └── exception_handlers.py
│   ├── models/                 # ORM 模型（13 个文件，15 张表）
│   ├── schemas/                # Pydantic 模型：请求校验 + 响应序列化
│   ├── repositories/           # 数据访问：select / func / 行锁
│   ├── services/               # 业务逻辑：事务、状态机、库存一致性
│   ├── controllers/            # 路由：参数、权限、响应
│   └── static/                 # 前端：index.html / styles.css / app.js
├── migrations/                 # Alembic 迁移（env.py + versions/）
├── sql/
│   ├── install.sql             # v2 全量建库建表（移植版/无 Python 环境用）
│   ├── create_tables.sql       # v1 基础表
│   ├── create_orders.sql       # v1 订单表
│   ├── insert_588_products.sql # 演示数据（588 个商品）
│   └── upgrade_v2.sql          # v1 → v2 增量升级
├── scripts/
│   └── mysql_concurrency_test.py  # 真实 MySQL 并发压测脚本
├── tests/                      # 10 个测试文件，48 个用例
├── docs/
│   ├── ARCHITECTURE.md         # 架构与代码说明（分层、事务、并发）
│   └── LIBRARIES.md            # 依赖库与常用函数手册
├── launcher.py                 # exe 启动器（切工作目录、选端口、开浏览器）
├── build_exe.ps1               # 一键打包脚本（产物输出到 ..\移植文件）
├── alembic.ini                 # 仅 ASCII，避免 Windows GBK 读取报错
├── pytest.ini / requirements*.txt / .env.example
└── README.md
```

---

## 4. 快速开始

### 4.1 环境要求

- Windows 10/11（Linux/macOS 同样可用，命令换成 `source .venv/bin/activate`）
- Python 3.11 以上
- MySQL 8.x 已启动，字符集 `utf8mb4`
- Redis 可选（不装也能跑）

### 4.2 安装依赖

```powershell
cd "d:\库存管理系统\库存管理系统\源码"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

只想要 exe、不想装 Python：直接看同级的 `移植文件` 目录，
或跳到 [13. 打包成 exe](#13-打包成-exe) / [14. 换电脑 / 局域网部署](#14-换电脑--局域网部署)。

### 4.3 配置 `.env`

复制 `.env.example` 为 `.env`，至少改数据库密码和 `SECRET_KEY`：

```text
DATABASE_URL=mysql+pymysql://root:你的密码@localhost:3306/库存管理系统?charset=utf8mb4
SECRET_KEY=请替换为至少32位的随机字符串
CACHE_ENABLED=false
```

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `mysql+pymysql://root:password@localhost:3306/库存管理系统?charset=utf8mb4` | 连接串，必须带 `charset=utf8mb4`，密码用你自己的 |
| `DB_ECHO` | `false` | 打印 SQL，排查问题时设 `true` |
| `MYSQL_TEST_URL` | 指向 `库存管理系统_test` | 真实并发测试用的独立库，留空则跳过 |
| `SECRET_KEY` | `dev-secret-key-change-me...` | **生产必须改**，否则 token 可被伪造 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | token 有效期（分钟） |
| `PASSWORD_HASH_ITERATIONS` | `120000` | PBKDF2 迭代次数 |
| `BOOTSTRAP_ADMIN` | `true` | 用户表为空时自动建管理员 |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `admin123` | 默认管理员 |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis 地址 |
| `CACHE_ENABLED` | `false` | 是否启用统计缓存 |
| `CACHE_TTL_SECONDS` | `30` | 缓存有效期 |
| `RATE_LIMIT_ENABLED` | `true` | 是否启用限流 |
| `RATE_LIMIT_DEFAULT_LIMIT` | `300` | 默认每窗口额度 |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | 限流窗口（秒） |

### 4.4 初始化数据库

**情况 A：全新数据库（推荐 Alembic）**

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

创建全部 15 张表并插入默认仓库 `MAIN / 主仓库`。需要演示数据再执行：

```powershell
mysql --default-character-set=utf8mb4 -u root -p 库存管理系统 < sql/insert_588_products.sql
```

**情况 B：用旧 SQL 脚本建过表的 v1 数据库**

```powershell
# 1. 备份（重要）
mysqldump -u root -p --default-character-set=utf8mb4 --single-transaction --no-tablespaces 库存管理系统 > backup.sql

# 2. 增量升级：新增表与字段，并把现有库存归入默认仓库
mysql --default-character-set=utf8mb4 -u root -p < sql/upgrade_v2.sql

# 3. 只标记版本，不要再次 upgrade（否则重复建表）
.\.venv\Scripts\python.exe -m alembic stamp 0001
```

> Windows 命令行传中文库名可能被 GBK 破坏。遇到 `Unknown database '???ϵͳ'`，
> 请用 Navicat / Workbench 导入，或用 Python 脚本调用（本项目就是这么做的）。

### 4.5 启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

| 地址 | 说明 |
|---|---|
| `http://127.0.0.1:8000/` | 中文管理页面（需登录） |
| `http://127.0.0.1:8000/docs` | Swagger UI，可点 Authorize 填 token |
| `http://127.0.0.1:8000/redoc` | ReDoc |
| `http://127.0.0.1:8000/health` | 健康检查，返回 `cache_backend` |

### 4.6 默认账号

```text
用户名：admin
密码：  admin123
```

首次启动时，仅当 `users` 表为空才创建；登录后请立即修改密码
（顶部「修改密码」或在用户管理中重置）。

---

## 5. 角色与权限

| 角色 | 说明 | 商品/库存 | 订单 | 任务 | 盘点/调拨 | 用户管理 |
|---|---|---|---|---|---|---|
| `admin` | 管理员 | 读写 | 读写 | 读写 | 读写 | ✅ |
| `operator` | 操作员 | 读写 | 读写 | 读写 | 读写 | ❌ |
| `viewer` | 只读用户 | 只读 | 只读 | 只读 | 只读 | ❌ |

- 权限在 Controller 层用 `Depends(require_login / require_operator / require_admin)` 声明。
- 只读用户写操作返回 `403 FORBIDDEN`；未登录或 token 过期返回 `401 UNAUTHORIZED`。
- 系统阻止把**最后一个启用的管理员**降级或禁用。
- 请求头：`Authorization: Bearer <access_token>`。

---

## 6. 核心业务规则

### 6.1 订单状态机与利润

```text
CREATED ──支付──▶ PAID ──退货──▶ PARTIALLY_RETURNED ──退完──▶ RETURNED
   │
   └──取消──▶ CANCELLED（回补库存，写 IN 流水）
```

- `PAID` 之后不能取消，只能走退货，避免"已收款又直接释放库存"。
- 退货按订单明细累计，`returned_quantity` 不能超过购买数量。
- 退款金额按**下单时单价快照**计算，商品后续改价不影响历史订单。

**利润计算**

```text
订单利润 = Σ ( unit_price − 商品当前成本价 ) × ( 数量 − 已退数量 )
累计利润 = 所有已支付订单（PAID / PARTIALLY_RETURNED / RETURNED）的利润之和
```

| 位置 | 展示内容 |
|---|---|
| 商品页利润卡片 | 累计利润、销售总额（已扣退款）、已支付订单数 |
| 订单列表「利润」列 | 每单利润，未支付订单标注「预计」 |
| 新建订单弹窗 | 合计金额 + 预计利润，随商品与数量实时变化 |
| 下单 / 支付提示 | toast 中直接显示本单利润 |

注意事项：

- 成本价取**商品当前** `products.cost`，不是下单时的快照。修改成本会回溯历史订单利润。
- 商品没填成本价时按 0 计算，此时利润等于销售额（偏高），建议给商品补成本价。
- 已取消订单利润恒为 0；退货部分不计入利润。
- 统计接口 `GET /api/orders/stats` 默认缓存 30 秒，支付 / 取消 / 退货后主动失效。

### 6.2 总库存与仓库库存

```text
products.quantity = Σ warehouse_stocks.quantity
```

- 旧数据没有仓库库存记录时，第一次参与仓库业务会把总库存初始化到默认仓库。
- 入库 / 出库 / 下单 / 取消 / 退货都同步维护默认仓库库存。
- 调拨在两个仓库之间一减一增，总库存不变，因此**不写**库存流水，调拨单即审计凭证。
- 盘点盘亏先扣默认仓库，不够再按仓库 ID 顺序扣其他仓库，避免对不上账。

### 6.3 防超卖

- 所有涉及库存的写操作都在事务中对商品行 `SELECT ... FOR UPDATE`。
- 多个商品按 `product_id` 排序依次加锁，降低交叉死锁概率。
- 库存不足抛 `InsufficientStockError`，整单回滚。
- SQLite 不支持行锁，所以另有真实 MySQL 并发测试（见第 12 节）。

### 6.4 盘点

```text
创建盘点单（快照 expected_quantity）
        ↓
录入 counted_quantity（可多次，最后一次为准）
        ↓
确认：有差异的商品写 ADJUST 流水，库存改为实盘数量
```

创建时保存账面快照，避免"创建后有人下单"导致差异计算失真。

### 6.5 调拨

```json
{
  "from_warehouse_id": 1,
  "to_warehouse_id": 2,
  "items": [{ "product_id": 1, "quantity": 4 }],
  "remark": "补货上海仓"
}
```

同一仓库调拨返回 422，源仓库库存不足返回 409。

---

## 7. API 清单

> 除 `/health`、`/`、`/api/auth/login` 外，所有接口都需要登录。

### 7.1 认证与用户

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/auth/login` | 公开 | 登录，限流 10 次/分钟/IP |
| GET | `/api/auth/me` | 登录 | 当前用户 |
| POST | `/api/auth/change-password` | 登录 | 修改自己的密码 |
| GET | `/api/users` | admin | 分页查询用户 |
| POST | `/api/users` | admin | 创建用户 |
| PATCH | `/api/users/{user_id}` | admin | 修改角色 / 状态 / 密码 |

```json
// POST /api/auth/login
{ "username": "admin", "password": "admin123" }

// 200
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 43200,
  "user": { "id": 1, "username": "admin", "role": "admin", "full_name": "系统管理员" }
}
```

### 7.2 分类与商品

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/categories` | 登录 | 全部分类 |
| GET | `/api/products` | 登录 | 分页，支持 `keyword` / `category_id` / `low_stock_only` |
| GET | `/api/products/stats` | 登录 | 库存统计（走缓存） |
| GET | `/api/products/low-stock` | 登录 | 低库存商品 |
| GET | `/api/products/{product_id}` | 登录 | 商品详情 |

```json
// GET /api/products?page=1&size=20&keyword=窗帘
{
  "items": [
    {
      "id": 1, "category_id": 1, "product_name": "窗帘-布帘-001", "sku": "CL-0001",
      "quantity": 94, "price": "199.00", "cost": "120.00",
      "unit": "件", "low_stock_threshold": 10
    }
  ],
  "total": 588, "page": 1, "size": 20
}
```

> 时间为方便阅读已省略，实际响应还包含 `last_inbound_at`、`last_outbound_at`、
> `created_at`、`updated_at`。

### 7.3 库存

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/inventory/inbound` | operator+ | 入库，同步默认仓库库存 |
| POST | `/api/inventory/outbound` | operator+ | 出库，库存不足返回 409 |
| GET | `/api/inventory/logs` | 登录 | 流水查询，支持 `product_id`、`change_type` |

流水类型：`IN` 入库、`OUT` 出库、`ADJUST` 盘点调整。

### 7.4 订单

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/orders` | operator+ | 下单并扣库存，限流 60 次/分钟/IP |
| GET | `/api/orders` | 登录 | 分页，支持 `status`、`keyword` |
| GET | `/api/orders/stats` | 登录 | 销售总额、已支付订单数、累计利润 |
| GET | `/api/orders/{order_id}` | 登录 | 详情（含明细、利润、退货记录） |
| POST | `/api/orders/{order_id}/pay` | operator+ | 支付 |
| POST | `/api/orders/{order_id}/cancel` | operator+ | 取消并回补库存 |
| POST | `/api/orders/{order_id}/returns` | operator+ | 退货（支持部分、多次） |
| GET | `/api/orders/{order_id}/returns` | 登录 | 退货记录 |

```json
// GET /api/orders/stats
{ "paid_order_count": 2, "total_revenue": "597.00", "total_profit": "237.00" }

// POST /api/orders/{id}/pay
{ "payment_method": "WECHAT", "operator": "admin" }

// POST /api/orders/{id}/returns
{ "items": [{ "order_item_id": 12, "quantity": 1 }], "reason": "尺码不合适" }
```

### 7.5 任务

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/tasks` | 登录 | 分页，支持 `keyword` / `status` / `priority` / `assignee` |
| GET | `/api/tasks/stats` | 登录 | 各状态数量 |
| POST | `/api/tasks` | operator+ | 创建任务 |
| GET | `/api/tasks/{task_id}` | 登录 | 任务详情 |
| PATCH | `/api/tasks/{task_id}` | operator+ | 局部更新（状态、优先级等） |
| DELETE | `/api/tasks/{task_id}` | operator+ | 删除，仅限已取消任务 |

状态：`PENDING / IN_PROGRESS / DONE / CANCELLED`；
优先级：`LOW / NORMAL / HIGH / URGENT`（列表按紧急程度排序）。
状态改为 `DONE` 自动写 `completed_at`，改回其他状态会清空。

### 7.6 盘点

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/stocktakes` | operator+ | 创建盘点单（默认全部商品，可指定分类/商品） |
| GET | `/api/stocktakes` | 登录 | 分页查询 |
| GET | `/api/stocktakes/{id}` | 登录 | 盘点单与明细 |
| POST | `/api/stocktakes/{id}/count` | operator+ | 批量录入实盘数量 |
| POST | `/api/stocktakes/{id}/confirm` | operator+ | 确认并调整库存 |
| POST | `/api/stocktakes/{id}/cancel` | operator+ | 取消盘点 |

### 7.7 调拨与仓库

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/warehouses` | 登录 | 仓库列表，首次访问自动创建 MAIN |
| POST | `/api/warehouses` | operator+ | 创建仓库（编码自动大写） |
| POST | `/api/transfers` | operator+ | 创建并完成调拨 |
| GET | `/api/transfers` | 登录 | 分页查询，可按仓库过滤 |
| GET | `/api/transfers/{id}` | 登录 | 调拨单详情 |

### 7.8 统一响应格式

成功：直接返回数据或分页结构 `{"items", "total", "page", "size"}`。

失败（所有业务异常同一格式）：

```json
{ "code": "INSUFFICIENT_STOCK", "message": "商品库存不足" }
```

| HTTP | code | 场景 |
|---|---|---|
| 401 | `UNAUTHORIZED` | 未登录 / token 过期 / 伪造 |
| 403 | `FORBIDDEN` | 角色权限不足 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 409 | `CONFLICT` / `INSUFFICIENT_STOCK` | 状态冲突 / 库存不足 |
| 422 | `VALIDATION_ERROR` | 参数校验失败（Pydantic） |
| 429 | `RATE_LIMITED` | 触发限流 |

---

## 8. 数据模型

| 表 | 说明 |
|---|---|
| `categories` | 商品分类 |
| `products` | 商品与**总库存**（含 `price` 售价、`cost` 成本价） |
| `inventory_logs` | 总库存变化流水（IN / OUT / ADJUST） |
| `orders` / `order_items` | 订单、明细（含 `returned_quantity`、`refunded_amount`） |
| `order_returns` / `order_return_items` | 退货单与退货明细 |
| `users` | 用户与角色 |
| `tasks` | 任务 |
| `warehouses` / `warehouse_stocks` | 仓库与仓库维度库存 |
| `stocktakes` / `stocktake_items` | 盘点单与明细 |
| `stock_transfers` / `stock_transfer_items` | 调拨单与明细 |

关键关系：

```text
categories 1 ── n products 1 ── n inventory_logs
orders 1 ── n order_items n ── 1 products
orders 1 ── n order_returns 1 ── n order_return_items
warehouses n ── n products（warehouse_stocks 中间表）
```

---

## 9. 缓存与限流

### 9.1 缓存

- 实现：`app/core/cache.py`，优先 Redis，连不上自动降级为进程内字典。
- 缓存内容与 key：

| 内容 | key | 失效时机 |
|---|---|---|
| 商品统计 | `inventory:products:stats` | 任何库存写操作后 |
| 订单经营统计 | `inventory:orders:stats` | 支付 / 取消 / 退货后 |

- 默认 TTL 30 秒，`CACHE_ENABLED=false` 时读写直接跳过。
- 启用 Redis：

```text
REDIS_URL=redis://127.0.0.1:6379/0
CACHE_ENABLED=true
CACHE_TTL_SECONDS=30
```

`GET /health` 返回 `cache_backend`（`redis` 或 `memory`）便于确认。

### 9.2 限流

固定窗口计数，key 为 `inventory:rl:<scope>:<客户端IP>`：

| 接口 | 限额 |
|---|---|
| 登录 `/api/auth/login` | 10 次 / 分钟 / IP |
| 下单 `POST /api/orders` | 60 次 / 分钟 / IP |
| 出入库 | 120 次 / 分钟 / IP |
| 其他未单独声明 | `RATE_LIMIT_DEFAULT_LIMIT`（默认 300） |

有 Redis 时多进程共享计数，无 Redis 时退化为单进程计数。
部署在 Nginx 后需要给 Uvicorn 加 `--proxy-headers` 才能取到真实 IP。

---

## 10. 数据库迁移

- `alembic.ini` 只放路径与日志配置，**不保存密码**；
- `migrations/env.py` 从 `settings.database_url` 读取连接；
- `alembic.ini` 有意保持 ASCII，避免 Windows 中文环境 GBK 读取报错。

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic history
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "新增字段"
.\.venv\Scripts\python.exe -m alembic upgrade head --sql > upgrade.sql
```

注意：迁移脚本使用 MySQL 方言（`BIGINT UNSIGNED`），单元测试不走 Alembic；
旧库请用 4.4 节的「升级 SQL + stamp」流程。

---

## 11. 前端使用说明

`http://127.0.0.1:8000/` 是无需构建的原生页面：

- **登录页**：token 存 localStorage，过期自动回登录页；
- **六个标签页**：商品库存、订单管理、任务管理、库存盘点、库存调拨、用户管理；
- **按钮按权限显示**：只读用户看不到写操作，非管理员看不到用户管理；
- **利润看板**：商品页顶部显示累计利润、销售总额、已支付订单数；
- **商品搜索**：新建订单时输入商品名称或 SKU 实时过滤，↑/↓ 选择、回车确认，
  不用在几百个商品的长列表里翻找；
- **订单列表**：每单显示利润（未支付标「预计」，已取消显示 `-`）；
- **订单操作**：支付、取消（填原因）、退货（选明细和数量）；
- **盘点 / 调拨**：创建盘点单、录入实盘、确认调差；创建仓库与调拨单；
- 接口 401 自动退出登录，错误信息以 toast 提示。

前端通过统一 `api()` 自动附加 `Authorization` 头并处理错误；
分页统一用 `bindPager()` / `renderPagerCore()` 绑定，页码由 `buildPagerItems()` 生成：
页数少时全部展开（`1 2 3`），页数多时折叠为 `1 … 5 6 7 … 30`，点页码直接跳转。

服务端对首页与 `/static` 下的文件禁用浏览器缓存
（`Cache-Control: no-cache, no-store, must-revalidate`），
更新前端后普通刷新即可生效；`index.html` 里引用资源还带了 `?v=日期` 版本号作为双保险。
修改前端时建议同步把两个版本号改成当天日期。

---

## 12. 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

当前 49 个用例（48 通过 + 1 个真实 MySQL 用例默认跳过），覆盖：

- 入库 / 出库 / 库存不足回滚 / 数量校验
- 商品搜索、库存统计、分页、订单利润与统计缓存
- 下单扣库存、重复商品合并、多商品订单、整单回滚
- 登录成功 / 密码错误 / 401 / 伪造 token
- 只读用户写操作 403、管理员创建用户、禁止降级最后一个管理员
- 订单支付、重复支付 409、取消回补库存
- 部分退货、全部退货、超量退货 409、未支付退货 409
- 任务 CRUD、优先级排序、完成时间、非法优先级 422、删除限制
- 盘点差异调整、取消盘点、重复确认 409
- 仓库调拨、总库存不变、仓库库存不足 409、同仓库调拨 422
- 统计缓存命中与失效、登录限流 429
- 管理页面与静态资源、健康检查

测试使用内存 SQLite + `Base.metadata.create_all()`，不依赖本机 MySQL。

**真实 MySQL 并发测试**（验证 `SELECT ... FOR UPDATE` 不超卖）：

```powershell
$env:MYSQL_TEST_URL = "mysql+pymysql://root:密码@localhost:3306/库存管理系统_test?charset=utf8mb4"
.\.venv\Scripts\python.exe -m pytest tests/test_mysql_concurrency.py -v

# 或独立压测脚本
.\.venv\Scripts\python.exe scripts\mysql_concurrency_test.py `
  --url "mysql+pymysql://root:密码@localhost:3306/库存管理系统?charset=utf8mb4" `
  --stock 10 --requests 20
```

并发用例流程：库存 10 的商品，20 个线程各下 1 件 → 断言成功 10 单、库存不足 10 单、
最终库存 0、出库流水 10 条。未设置 `MYSQL_TEST_URL` 时自动跳过。

---

## 13. 打包成 exe

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

打包产物会输出到同级的 `移植文件` 目录（源码目录里不生成 exe）：

```text
库存管理系统/
├── 源码/                      # 打包脚本在这里执行
└── 移植文件/
    ├── InventoryManager.exe   # ★ 双击启动
    ├── static/                # 前端文件（改页面只需替换这里）
    └── .env.example           # 配置模板，复制成 .env 后修改
```

- **日常启动**：双击 `移植文件\InventoryManager.exe`。
- 双击后会启动服务并自动打开浏览器；端口从 8000 开始找空闲端口。
- exe 仍需本机 MySQL，`.env` 放在 exe 同目录（`移植文件` 下）。
- 前端查找顺序：`<exe目录>\static` → `<exe目录>\app\static` → exe 内置。
  `移植文件\static` 存在时优先用它，**改页面只需覆盖这个目录，不用重新打包**。
- **改了 Python 代码**：重新执行 `build_exe.ps1`，会自动更新 `移植文件` 里的 exe。
- `launcher.py` 支持 `--no-browser` 参数，适合作为服务常驻启动。

---

## 14. 换电脑 / 局域网部署

### 14.1 单机换电脑（不装 Python）

1. 源机器导出数据库（推荐 Navicat / Workbench，避免中文库名乱码）
2. 目标机器安装 MySQL 8，建同名库并导入数据：

```powershell
mysql --default-character-set=utf8mb4 -u root -p -e "CREATE DATABASE 库存管理系统 DEFAULT CHARSET utf8mb4"
mysql --default-character-set=utf8mb4 -u root -p 库存管理系统 < backup.sql
```

3. 把整个 `移植文件` 目录拷到目标机器（exe + `static` + `.env.example`）。
   **不要复制 `源码\.venv`**，它绑定本机路径，拷过去也用不了
4. 在 exe 同目录（`移植文件`）建 `.env`：

```text
DATABASE_URL=mysql+pymysql://root:目标机密码@127.0.0.1:3306/库存管理系统?charset=utf8mb4
SECRET_KEY=换成一串随机长字符串
CACHE_ENABLED=false
```

5. 双击 `InventoryManager.exe`，用原库里的账号登录。

### 14.2 局域网多人使用

默认 exe 只监听 `127.0.0.1`，其他电脑访问不到。需要：

1. 数据库放到一台常开的机器（服务器），MySQL 允许远程连接
   （`bind-address=0.0.0.0` + 授权该库给远程账号）；
2. 其他机器的 `.env` 里把 `127.0.0.1` 改成服务器 IP；
3. 服务监听所有网卡：把 `launcher.py` 中 `uvicorn.run(..., host="127.0.0.1")`
   改成 `host="0.0.0.0"` 后重新打包，或直接用源码启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

4. 放行 Windows 防火墙 8000 端口，其他人访问 `http://服务器IP:8000`。

### 14.3 注意事项

- `SECRET_KEY` 必须换：默认值公开，等于谁都能伪造登录 token。
- 数据全在 MySQL，**定期备份**（`mysqldump` 或 Workbench 导出）。
- 字符集必须是 `utf8mb4`，否则中文商品名、备注会乱码。
- 多实例部署时用 Redis，否则内存缓存与限流计数各进程独立。

---

## 15. 常见问题

### 1. 所有接口都返回 401

```json
{ "code": "UNAUTHORIZED", "message": "请先登录后再访问该接口" }
```

检查请求头 `Authorization: Bearer <token>` 是否带上；token 默认 12 小时过期；
改了 `SECRET_KEY` 会让所有旧 token 立即失效。Swagger 里点右上角 Authorize 填 token。

### 2. `Table 'xxx.users' doesn't exist`

数据库还是 v1 结构，执行 `sql/upgrade_v2.sql`，然后 `alembic stamp 0001`。

### 3. `Unknown column 'paid_at' in 'field list'`

同上，v2 新增了 `orders.paid_at` 等字段，跑升级脚本即可。

### 4. Alembic 报 `UnicodeDecodeError: 'gbk' codec can't decode`

`alembic.ini` 里写了中文注释。保持该文件纯 ASCII，或另存为 UTF-8。

### 5. 启动日志显示「Redis 不可用，已降级为内存缓存」

本地没装 Redis 或没启动，属正常现象。需要真缓存时：

```powershell
redis-server
# 再把 .env 里的 CACHE_ENABLED 改为 true
```

### 6. SQLite 测试通过，是否代表 MySQL 并发安全？

不代表。SQLite 不支持行锁，必须跑 `tests/test_mysql_concurrency.py` 验证。

### 7. 盘亏数量超过默认仓库库存

默认仓库不够时会按仓库 ID 顺序继续扣其他仓库；所有仓库都不够则报错，
需要先调拨或修正历史库存。

### 8. 改成前端后页面没变化

如果访问的是 exe：把 `源码\app\static` 覆盖到 `移植文件\static`；
如果还是旧的，浏览器按一次 `Ctrl + F5`（服务端已禁用静态缓存，正常刷新即可）。
改了 Python 代码则必须重新执行 `build_exe.ps1`。

### 9. 新建订单时商品搜不到

商品搜索是在已加载的商品集合里过滤（启动时最多加载 3000 条），超出会有提示；
真正商品很多时建议用后端关键字搜索（`GET /api/products?keyword=`）扩展。

### 10. 利润数字和手工算的对不上

利润按**商品当前成本价**计算，且退货部分不计入。历史订单会随成本修改而变化；
商品没填成本价时按 0 处理，利润会偏高。需要精确核算应引入"下单时成本快照"。

---

## 16. 开发约定

- **分层**：Controller 只做参数/权限/响应；Service 负责事务与业务规则；
  Repository 只写查询；Model 不放业务逻辑。
- **异常**：业务层抛 `app.core.exceptions` 下的异常，由全局处理器转 JSON，
  不在 Service 里返回 HTTP 状态码。
- **事务**：`commit` / `rollback` 只出现在 Service，Repository 不提交。
- **金额**：统一 `Decimal` + `Numeric(10, 2)`，禁止用 `float` 计算。
- **命名**：模块 `xxx_controller/service/repo.py`，常量全大写，私有函数前缀 `_`。
- **注释**：中文说明"为什么"，函数用 Google 风格 docstring。
- **前端**：一个 `api()` 统一请求、`bindPager()` 统一分页、`toast()` 统一提示。

---

## 17. 文档

| 文档 | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 分层架构、请求生命周期、事务与并发、异常处理、设计取舍 |
| [docs/LIBRARIES.md](docs/LIBRARIES.md) | 依赖库手册：本项目用到的函数 + 同版本常用函数 |
| `/docs`（服务启动后） | Swagger UI，可直接调试接口 |
| `/redoc` | ReDoc，适合阅读接口结构 |

---

## 18. 后续可扩展

- 利润核算改为"下单时成本快照"（`order_items` 加 `unit_cost` 字段 + 迁移）
- 订单导出 Excel / 打印小票
- 供应商与采购入库单
- 多用户操作日志（谁改了库存、谁退了货）
- 库存变动统一收口（`StockMutator`），目前三处实现各自事务
- 前端拆分模块化（当前单文件 `app.js`，约 1700 行）
