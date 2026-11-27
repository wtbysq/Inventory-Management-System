# 库存管理系统

基于 **FastAPI + SQLAlchemy 2.x + MySQL 8** 的进销存系统，
自带中文管理页面，可打包成单个 exe 分发。

支持商品库存、订单（下单/支付/取消/退货/利润统计）、任务管理、库存盘点、
仓库调拨、用户登录与角色权限，前端为原生 HTML/CSS/JS，无框架、无构建步骤。

## 仓库结构

```text
库存管理系统/
├── 源码/          # 开发用：Python 源码、测试、迁移、SQL、文档
└── 移植文件/      # 开箱即用：exe + 前端 + SQL 脚本 + 使用说明
```

## 快速开始

### 方式一：直接用 exe（不需要 Python）

1. 从本仓库 [Releases](../../releases) 下载最新的 `InventoryManager.exe`，
   放到 `移植文件/` 目录下（exe 体积较大，不随源码提交）
2. 安装 MySQL 8 并启动
3. 把 `移植文件/sql/install.sql` 导入（建库 + 15 张表）
4. 把 `移植文件/.env.example` 复制为 `.env`，填数据库密码
5. 双击 `移植文件/InventoryManager.exe`，浏览器打开 <http://127.0.0.1:8000>
6. 默认账号 `admin / admin123`（首次启动自动创建，请立即修改）

详细步骤见 [移植文件/使用说明.txt](移植文件/使用说明.txt)。

### 方式二：跑源码

```powershell
cd 源码
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# 建库：任选其一
alembic upgrade head
# 或 mysql --default-character-set=utf8mb4 -u root -p < sql/install.sql

# 配置 .env 后启动
python -m uvicorn app.main:app --reload
```

访问 `http://127.0.0.1:8000/`（管理页面）、`/docs`（Swagger）。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI、Uvicorn、Pydantic v2、pydantic-settings |
| 数据 | SQLAlchemy 2.x、PyMySQL、MySQL 8、Alembic |
| 前端 | 原生 HTML5 / CSS3 / JavaScript（ES6+） |
| 缓存限流 | Redis（可选，不可用时自动降级内存缓存） |
| 测试 | PyTest、HTTPX（48 passed, 1 skipped） |
| 打包 | PyInstaller（单文件 exe） |

## 功能特性

- 商品：分页搜索、分类筛选、低库存预警、库存统计
- 库存：入库 / 出库流水，行锁防超卖
- 订单：下单扣库存、支付、取消回补、部分/全部退货、**订单利润与累计利润看板**
- 任务：CRUD、状态流转、优先级排序
- 盘点：账面快照、实盘录入、确认调差
- 调拨：多仓库、调拨单审计
- 权限：JWT + PBKDF2，admin / operator / viewer 三种角色
- 前端细节：下单时商品实时搜索、页码分页（`1 … 5 6 7 … 30`）、静态资源禁缓存

## 文档

- [源码/README.md](源码/README.md)：安装、配置、API 清单、常见问题
- [源码/docs/ARCHITECTURE.md](源码/docs/ARCHITECTURE.md)：分层架构、事务与并发设计
- [源码/docs/LIBRARIES.md](源码/docs/LIBRARIES.md)：依赖库与本项目常用函数手册
- [源码/sql/README.md](源码/sql/README.md)：各 SQL 脚本用途与执行顺序

## 注意

- `.env` 含数据库密码，已在 `.gitignore` 中排除，请勿提交
- `InventoryManager.exe`（约 28 MB）不进 Git，请从 [Releases](../../releases) 下载；重新打包方法见 [源码/README.md](源码/README.md)
- 生产环境务必更换 `SECRET_KEY`
- 移植版默认只监听 `127.0.0.1`，局域网使用需改 `launcher.py` 的 host 并重新打包
