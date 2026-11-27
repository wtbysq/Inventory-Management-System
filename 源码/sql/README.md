# SQL 脚本说明

脚本分三类：**全量安装**（`install.sql`，移植版首选）、
**v1 遗留建表**（老环境保留）、**升级**（v1 → v2）。

| 脚本 | 作用 | 适用场景 |
|---|---|---|
| `install.sql` | **v2 全量建库建表**：15 张表 + 默认仓库，幂等（IF NOT EXISTS） | 全新安装、移植版部署 |
| `create_tables.sql` | 建库 + 分类表 + 商品表 + 库存流水表 | 只想跑 v1 结构的老环境 |
| `create_orders.sql` | 建订单表 + 订单明细表 | 需先执行 `create_tables.sql` |
| `insert_588_products.sql` | 插入 7 个分类、588 个演示商品 | 演示 / 测试数据 |
| `upgrade_v2.sql` | v1 → v2：加用户、任务、退货、仓库、盘点、调拨表与订单字段 | **已有 v1 数据的库** |

> `install.sql` 与 Alembic 的 `0001_initial_schema` 等价（直接从当前库 `SHOW CREATE TABLE` 导出），
> 移植版没有 Python 环境，用它建库最省事。

## 1. 执行顺序

```text
全新库 · 没装 Python（移植版）：
    mysql ... < sql/install.sql
    （可选）mysql ... < sql/demo_data.sql

全新库 · 有 Python（源码）：
    alembic upgrade head
    （可选）mysql ... < sql/insert_588_products.sql

老 v1 库升级到 v2：
    mysqldump 备份
        ↓
    mysql ... < sql/upgrade_v2.sql
        ↓
    alembic stamp 0001      ← 只打标记，不要再 upgrade
```

## 2. 常用命令

```powershell
# 建议先备份
mysqldump -u root -p --default-character-set=utf8mb4 --single-transaction --no-tablespaces 库存管理系统 > backup.sql

# 全新安装：建库 + 15 张表 + 默认仓库
mysql --default-character-set=utf8mb4 -u root -p < sql/install.sql

# 执行升级脚本（脚本内部已写 USE，命令行不用带库名）
mysql --default-character-set=utf8mb4 -u root -p < sql/upgrade_v2.sql

# 演示数据
mysql --default-character-set=utf8mb4 -u root -p < sql/insert_588_products.sql
```

> Windows 下 `mysql` / `mysqldump` 命令行的中文库名可能被 GBK 破坏，
> 报 `Unknown database '???ϵͳ'` 时改用 Navicat / Workbench 导入，或用 Python 脚本调用。

## 3. 注意事项

- `install.sql` 是幂等的（`CREATE ... IF NOT EXISTS`），重复执行不会删数据，
  但也不会修改已存在表的结构；结构变更请走 `upgrade_v2.sql` 或 Alembic。
- `upgrade_v2.sql` **只能执行一次**，重复执行会报「列已存在」。
- 升级后必须 `alembic stamp 0001`，否则 Alembic 认为库是空的，`upgrade` 会重复建表。
- `create_tables.sql` / `create_orders.sql` 是 v1 脚本，**不要**在已用 Alembic 建好的库上执行。
- 演示数据使用 `INSERT IGNORE`，重复执行不会报错，但也不会更新已有商品。
