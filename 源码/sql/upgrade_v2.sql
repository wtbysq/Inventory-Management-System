-- =====================================================================
-- v2 升级脚本：登录权限、任务、订单支付/取消/退货、盘点、仓库调拨
--
-- 适用：已经执行过 create_tables.sql + create_orders.sql 的旧库。
-- 执行：mysql --default-character-set=utf8mb4 -u root -p < upgrade_v2.sql
--
-- 注意：
--   1. 本脚本只执行一次，重复执行会提示列已存在。
--   2. 执行完成后可运行 `alembic stamp 0001` 记录版本。
--   3. 建议先备份：mysqldump -u root -p 库存管理系统 > backup.sql
-- =====================================================================

USE `库存管理系统`;

-- ---------------------------------------------------------------------
-- 1. 订单表：支付、取消、退款字段
-- ---------------------------------------------------------------------
ALTER TABLE orders
  ADD COLUMN paid_at DATETIME NULL COMMENT '支付时间' AFTER remark,
  ADD COLUMN payment_method VARCHAR(32) NULL COMMENT '支付方式' AFTER paid_at,
  ADD COLUMN cancelled_at DATETIME NULL COMMENT '取消时间' AFTER payment_method,
  ADD COLUMN cancel_reason VARCHAR(255) NULL COMMENT '取消原因' AFTER cancelled_at,
  ADD COLUMN refunded_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '累计退款金额' AFTER cancel_reason;

-- 订单状态扩展为：
--   CREATED / PAID / CANCELLED / PARTIALLY_RETURNED / RETURNED
ALTER TABLE orders
  MODIFY COLUMN status VARCHAR(16) NOT NULL DEFAULT 'CREATED'
  COMMENT 'CREATED/PAID/CANCELLED/PARTIALLY_RETURNED/RETURNED';

-- ---------------------------------------------------------------------
-- 2. 订单明细：累计已退数量
-- ---------------------------------------------------------------------
ALTER TABLE order_items
  ADD COLUMN returned_quantity INT NOT NULL DEFAULT 0 COMMENT '累计已退数量' AFTER subtotal;

-- ---------------------------------------------------------------------
-- 3. 库存流水：类型从 ENUM 改为 VARCHAR，支持盘点调整
-- ---------------------------------------------------------------------
ALTER TABLE inventory_logs
  MODIFY COLUMN change_type VARCHAR(16) NOT NULL
  COMMENT 'IN入库 OUT出库 ADJUST盘点调整',
  ADD INDEX idx_log_change_type (change_type);

-- ---------------------------------------------------------------------
-- 4. 用户表
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE COMMENT '登录名',
  password_hash VARCHAR(255) NOT NULL COMMENT 'PBKDF2 密码哈希',
  full_name VARCHAR(64) NULL COMMENT '显示名称',
  role VARCHAR(16) NOT NULL DEFAULT 'operator' COMMENT 'admin/operator/viewer',
  is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  last_login_at DATETIME NULL COMMENT '最近登录时间',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  INDEX idx_users_role (role),
  INDEX idx_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- ---------------------------------------------------------------------
-- 5. 任务表
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(128) NOT NULL COMMENT '任务标题',
  description TEXT NULL COMMENT '任务描述',
  status VARCHAR(16) NOT NULL DEFAULT 'PENDING'
    COMMENT 'PENDING/IN_PROGRESS/DONE/CANCELLED',
  priority VARCHAR(16) NOT NULL DEFAULT 'NORMAL'
    COMMENT 'LOW/NORMAL/HIGH/URGENT',
  assignee VARCHAR(64) NULL COMMENT '负责人',
  due_at DATETIME NULL COMMENT '截止时间',
  completed_at DATETIME NULL COMMENT '完成时间',
  created_by VARCHAR(64) NULL COMMENT '创建人',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  INDEX idx_tasks_title (title),
  INDEX idx_tasks_status (status),
  INDEX idx_tasks_priority (priority),
  INDEX idx_tasks_assignee (assignee)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务表';

-- ---------------------------------------------------------------------
-- 6. 退货单
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_returns (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  return_no VARCHAR(64) NOT NULL UNIQUE COMMENT '退货单号',
  order_id BIGINT UNSIGNED NOT NULL COMMENT '原订单ID',
  refund_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '本次退款金额',
  reason VARCHAR(255) NULL COMMENT '退货原因',
  operator VARCHAR(64) NULL COMMENT '操作人',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_order_returns_order
    FOREIGN KEY (order_id) REFERENCES orders(id),

  INDEX idx_order_returns_order (order_id),
  INDEX idx_order_returns_no (return_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单退货单';

CREATE TABLE IF NOT EXISTS order_return_items (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  return_id BIGINT UNSIGNED NOT NULL COMMENT '退货单ID',
  order_item_id BIGINT UNSIGNED NOT NULL COMMENT '原订单明细ID',
  product_id BIGINT UNSIGNED NOT NULL COMMENT '商品ID',
  product_name VARCHAR(128) NOT NULL COMMENT '商品名称快照',
  sku VARCHAR(64) NOT NULL COMMENT 'SKU快照',
  quantity INT NOT NULL COMMENT '退货数量',
  unit_price DECIMAL(10, 2) NOT NULL COMMENT '单价',
  subtotal DECIMAL(12, 2) NOT NULL COMMENT '退款小计',

  CONSTRAINT fk_return_items_return
    FOREIGN KEY (return_id) REFERENCES order_returns(id),
  CONSTRAINT fk_return_items_order_item
    FOREIGN KEY (order_item_id) REFERENCES order_items(id),
  CONSTRAINT fk_return_items_product
    FOREIGN KEY (product_id) REFERENCES products(id),

  INDEX idx_return_items_return (return_id),
  INDEX idx_return_items_order_item (order_item_id),
  INDEX idx_return_items_product (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单退货明细';

-- ---------------------------------------------------------------------
-- 7. 仓库与仓库库存
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouses (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(32) NOT NULL UNIQUE COMMENT '仓库编码',
  name VARCHAR(64) NOT NULL COMMENT '仓库名称',
  address VARCHAR(255) NULL COMMENT '仓库地址',
  is_default TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否默认仓库',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  INDEX idx_warehouses_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仓库表';

CREATE TABLE IF NOT EXISTS warehouse_stocks (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  warehouse_id BIGINT UNSIGNED NOT NULL COMMENT '仓库ID',
  product_id BIGINT UNSIGNED NOT NULL COMMENT '商品ID',
  quantity INT NOT NULL DEFAULT 0 COMMENT '该仓库库存',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  CONSTRAINT uk_warehouse_product UNIQUE (warehouse_id, product_id),
  CONSTRAINT fk_warehouse_stocks_warehouse
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
  CONSTRAINT fk_warehouse_stocks_product
    FOREIGN KEY (product_id) REFERENCES products(id),

  INDEX idx_warehouse_stocks_warehouse (warehouse_id),
  INDEX idx_warehouse_stocks_product (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仓库维度库存';

-- ---------------------------------------------------------------------
-- 8. 盘点单
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stocktakes (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  stocktake_no VARCHAR(64) NOT NULL UNIQUE COMMENT '盘点单号',
  status VARCHAR(16) NOT NULL DEFAULT 'COUNTING'
    COMMENT 'COUNTING/CONFIRMED/CANCELLED',
  scope VARCHAR(128) NULL COMMENT '盘点范围描述',
  operator VARCHAR(64) NULL COMMENT '盘点人',
  remark VARCHAR(255) NULL COMMENT '备注',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  confirmed_at DATETIME NULL COMMENT '确认时间',

  INDEX idx_stocktakes_no (stocktake_no),
  INDEX idx_stocktakes_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='库存盘点单';

CREATE TABLE IF NOT EXISTS stocktake_items (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  stocktake_id BIGINT UNSIGNED NOT NULL COMMENT '盘点单ID',
  product_id BIGINT UNSIGNED NOT NULL COMMENT '商品ID',
  sku VARCHAR(64) NOT NULL COMMENT 'SKU快照',
  product_name VARCHAR(128) NOT NULL COMMENT '商品名称快照',
  expected_quantity INT NOT NULL COMMENT '账面数量（创建时快照）',
  counted_quantity INT NULL COMMENT '实盘数量',
  difference INT NULL COMMENT '差异 = 实盘 - 账面',
  remark VARCHAR(255) NULL COMMENT '备注',

  CONSTRAINT fk_stocktake_items_stocktake
    FOREIGN KEY (stocktake_id) REFERENCES stocktakes(id),
  CONSTRAINT fk_stocktake_items_product
    FOREIGN KEY (product_id) REFERENCES products(id),

  INDEX idx_stocktake_items_stocktake (stocktake_id),
  INDEX idx_stocktake_items_product (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='库存盘点明细';

-- ---------------------------------------------------------------------
-- 9. 调拨单
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_transfers (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  transfer_no VARCHAR(64) NOT NULL UNIQUE COMMENT '调拨单号',
  from_warehouse_id BIGINT UNSIGNED NOT NULL COMMENT '调出仓库ID',
  to_warehouse_id BIGINT UNSIGNED NOT NULL COMMENT '调入仓库ID',
  status VARCHAR(16) NOT NULL DEFAULT 'COMPLETED'
    COMMENT 'COMPLETED/CANCELLED',
  operator VARCHAR(64) NULL COMMENT '操作人',
  remark VARCHAR(255) NULL COMMENT '备注',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_stock_transfers_from
    FOREIGN KEY (from_warehouse_id) REFERENCES warehouses(id),
  CONSTRAINT fk_stock_transfers_to
    FOREIGN KEY (to_warehouse_id) REFERENCES warehouses(id),

  INDEX idx_stock_transfers_no (transfer_no),
  INDEX idx_stock_transfers_status (status),
  INDEX idx_stock_transfers_from (from_warehouse_id),
  INDEX idx_stock_transfers_to (to_warehouse_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='库存调拨单';

CREATE TABLE IF NOT EXISTS stock_transfer_items (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  transfer_id BIGINT UNSIGNED NOT NULL COMMENT '调拨单ID',
  product_id BIGINT UNSIGNED NOT NULL COMMENT '商品ID',
  sku VARCHAR(64) NOT NULL COMMENT 'SKU快照',
  product_name VARCHAR(128) NOT NULL COMMENT '商品名称快照',
  quantity INT NOT NULL COMMENT '调拨数量',

  CONSTRAINT fk_transfer_items_transfer
    FOREIGN KEY (transfer_id) REFERENCES stock_transfers(id),
  CONSTRAINT fk_transfer_items_product
    FOREIGN KEY (product_id) REFERENCES products(id),

  INDEX idx_transfer_items_transfer (transfer_id),
  INDEX idx_transfer_items_product (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='库存调拨明细';

-- ---------------------------------------------------------------------
-- 10. 初始化默认仓库
-- ---------------------------------------------------------------------
INSERT INTO warehouses (code, name, is_default)
SELECT 'MAIN', '主仓库', 1
WHERE NOT EXISTS (SELECT 1 FROM warehouses WHERE code = 'MAIN');

-- 把现有总库存全部归入默认仓库，保证：
--   products.quantity = sum(warehouse_stocks.quantity)
INSERT INTO warehouse_stocks (warehouse_id, product_id, quantity)
SELECT w.id, p.id, p.quantity
FROM products p
CROSS JOIN warehouses w
WHERE w.code = 'MAIN'
  AND NOT EXISTS (
    SELECT 1 FROM warehouse_stocks s
    WHERE s.warehouse_id = w.id AND s.product_id = p.id
  );

-- ---------------------------------------------------------------------
-- 11. 默认管理员
-- ---------------------------------------------------------------------
-- 应用启动时会自动创建（仅当 users 表为空）：
--   用户名 admin / 密码 admin123
-- 也可以在这里手动插入，但密码必须使用 PBKDF2 哈希，不能写明文。
-- 建议启动服务后立刻登录并修改密码。
