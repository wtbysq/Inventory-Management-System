-- =====================================================================
-- 库存管理系统 v2 · 初始化脚本（全新安装用）
--
-- 用法（Windows PowerShell / CMD 均可）：
--     mysql --default-character-set=utf8mb4 -u root -p < sql\install.sql
--
-- 作用：
--     1. 创建数据库 `库存管理系统`（已存在则跳过）
--     2. 创建全部 15 张业务表（已存在则跳过，不会删数据）
--     3. 插入默认仓库 MAIN / 主仓库
--
-- 注意：
--     - 已有 v1 老库需要保留数据时，请执行 upgrade_v2.sql，不要执行本脚本。
--     - 执行完后首次启动程序会自动创建管理员 admin / admin123。
--     - 演示商品数据可选执行 demo_data.sql。
-- =====================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE DATABASE IF NOT EXISTS `库存管理系统`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `库存管理系统`;

CREATE TABLE IF NOT EXISTS `categories` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `category_name` varchar(32) NOT NULL COMMENT '分类名称',
  `sku_prefix` varchar(8) NOT NULL COMMENT 'SKU前缀',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `category_name` (`category_name`),
  UNIQUE KEY `sku_prefix` (`sku_prefix`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='商品分类表';

CREATE TABLE IF NOT EXISTS `inventory_logs` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `product_id` bigint unsigned NOT NULL COMMENT '商品ID',
  `change_type` varchar(16) NOT NULL COMMENT 'IN入库 OUT出库 ADJUST盘点调整',
  `change_quantity` int NOT NULL COMMENT '变动数量',
  `before_quantity` int NOT NULL COMMENT '变动前库存',
  `after_quantity` int NOT NULL COMMENT '变动后库存',
  `operated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
  `operator` varchar(64) DEFAULT NULL COMMENT '操作人',
  `remark` varchar(255) DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`id`),
  KEY `idx_log_product` (`product_id`),
  KEY `idx_log_operated_at` (`operated_at`),
  KEY `idx_log_change_type` (`change_type`),
  CONSTRAINT `fk_logs_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`),
  CONSTRAINT `chk_log_quantity` CHECK ((`change_quantity` > 0))
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='出入库流水表';

CREATE TABLE IF NOT EXISTS `order_items` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '明细ID',
  `order_id` bigint unsigned NOT NULL COMMENT '订单ID',
  `product_id` bigint unsigned NOT NULL COMMENT '商品ID',
  `product_name` varchar(128) NOT NULL COMMENT '下单时的商品名称',
  `sku` varchar(64) NOT NULL COMMENT '下单时的商品SKU',
  `quantity` int NOT NULL COMMENT '购买数量',
  `unit_price` decimal(10,2) NOT NULL COMMENT '下单时的单价',
  `subtotal` decimal(12,2) NOT NULL COMMENT '小计金额：unit_price * quantity',
  `returned_quantity` int NOT NULL DEFAULT '0' COMMENT '累计已退数量',
  PRIMARY KEY (`id`),
  KEY `ix_order_items_order_id` (`order_id`),
  KEY `ix_order_items_product_id` (`product_id`),
  CONSTRAINT `order_items_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`),
  CONSTRAINT `order_items_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `order_return_items` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `return_id` bigint unsigned NOT NULL COMMENT '退货单ID',
  `order_item_id` bigint unsigned NOT NULL COMMENT '原订单明细ID',
  `product_id` bigint unsigned NOT NULL COMMENT '商品ID',
  `product_name` varchar(128) NOT NULL COMMENT '商品名称快照',
  `sku` varchar(64) NOT NULL COMMENT 'SKU快照',
  `quantity` int NOT NULL COMMENT '退货数量',
  `unit_price` decimal(10,2) NOT NULL COMMENT '单价',
  `subtotal` decimal(12,2) NOT NULL COMMENT '退款小计',
  PRIMARY KEY (`id`),
  KEY `idx_return_items_return` (`return_id`),
  KEY `idx_return_items_order_item` (`order_item_id`),
  KEY `idx_return_items_product` (`product_id`),
  CONSTRAINT `fk_return_items_order_item` FOREIGN KEY (`order_item_id`) REFERENCES `order_items` (`id`),
  CONSTRAINT `fk_return_items_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`),
  CONSTRAINT `fk_return_items_return` FOREIGN KEY (`return_id`) REFERENCES `order_returns` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单退货明细';

CREATE TABLE IF NOT EXISTS `order_returns` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `return_no` varchar(64) NOT NULL COMMENT '退货单号',
  `order_id` bigint unsigned NOT NULL COMMENT '原订单ID',
  `refund_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '本次退款金额',
  `reason` varchar(255) DEFAULT NULL COMMENT '退货原因',
  `operator` varchar(64) DEFAULT NULL COMMENT '操作人',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `return_no` (`return_no`),
  KEY `idx_order_returns_order` (`order_id`),
  KEY `idx_order_returns_no` (`return_no`),
  CONSTRAINT `fk_order_returns_order` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单退货单';

CREATE TABLE IF NOT EXISTS `orders` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '订单ID',
  `order_no` varchar(64) NOT NULL COMMENT '订单号，全局唯一',
  `total_amount` decimal(12,2) NOT NULL COMMENT '订单总金额',
  `status` varchar(16) NOT NULL DEFAULT 'CREATED' COMMENT 'CREATED/PAID/CANCELLED/PARTIALLY_RETURNED/RETURNED',
  `operator` varchar(64) DEFAULT NULL COMMENT '下单人',
  `remark` varchar(255) DEFAULT NULL COMMENT '订单备注',
  `paid_at` datetime DEFAULT NULL COMMENT '支付时间',
  `payment_method` varchar(32) DEFAULT NULL COMMENT '支付方式',
  `cancelled_at` datetime DEFAULT NULL COMMENT '取消时间',
  `cancel_reason` varchar(255) DEFAULT NULL COMMENT '取消原因',
  `refunded_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '累计退款金额',
  `created_at` datetime NOT NULL DEFAULT (now()) COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT (now()) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_orders_order_no` (`order_no`),
  KEY `ix_orders_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `products` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `category_id` int unsigned NOT NULL COMMENT '商品分类ID',
  `product_name` varchar(128) NOT NULL COMMENT '商品名称',
  `sku` varchar(64) NOT NULL COMMENT '商品SKU',
  `quantity` int NOT NULL DEFAULT '0' COMMENT '当前库存数量',
  `price` decimal(10,2) NOT NULL COMMENT '销售价格',
  `cost` decimal(10,2) DEFAULT NULL COMMENT '成本价，用于统计库存价值',
  `unit` varchar(16) NOT NULL DEFAULT '件' COMMENT '单位',
  `low_stock_threshold` int NOT NULL DEFAULT '10' COMMENT '低库存阈值',
  `last_inbound_at` datetime DEFAULT NULL COMMENT '最近一次入库时间',
  `last_outbound_at` datetime DEFAULT NULL COMMENT '最近一次出库时间',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `sku` (`sku`),
  KEY `idx_product_name` (`product_name`),
  KEY `idx_category_id` (`category_id`),
  KEY `idx_stock` (`quantity`,`low_stock_threshold`),
  CONSTRAINT `fk_products_category` FOREIGN KEY (`category_id`) REFERENCES `categories` (`id`),
  CONSTRAINT `chk_products_price` CHECK ((`price` >= 0)),
  CONSTRAINT `chk_products_quantity` CHECK ((`quantity` >= 0))
) ENGINE=InnoDB AUTO_INCREMENT=589 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='商品表';

CREATE TABLE IF NOT EXISTS `stock_transfer_items` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `transfer_id` bigint unsigned NOT NULL COMMENT '调拨单ID',
  `product_id` bigint unsigned NOT NULL COMMENT '商品ID',
  `sku` varchar(64) NOT NULL COMMENT 'SKU快照',
  `product_name` varchar(128) NOT NULL COMMENT '商品名称快照',
  `quantity` int NOT NULL COMMENT '调拨数量',
  PRIMARY KEY (`id`),
  KEY `idx_transfer_items_transfer` (`transfer_id`),
  KEY `idx_transfer_items_product` (`product_id`),
  CONSTRAINT `fk_transfer_items_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`),
  CONSTRAINT `fk_transfer_items_transfer` FOREIGN KEY (`transfer_id`) REFERENCES `stock_transfers` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='库存调拨明细';

CREATE TABLE IF NOT EXISTS `stock_transfers` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `transfer_no` varchar(64) NOT NULL COMMENT '调拨单号',
  `from_warehouse_id` bigint unsigned NOT NULL COMMENT '调出仓库ID',
  `to_warehouse_id` bigint unsigned NOT NULL COMMENT '调入仓库ID',
  `status` varchar(16) NOT NULL DEFAULT 'COMPLETED' COMMENT 'COMPLETED/CANCELLED',
  `operator` varchar(64) DEFAULT NULL COMMENT '操作人',
  `remark` varchar(255) DEFAULT NULL COMMENT '备注',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `transfer_no` (`transfer_no`),
  KEY `idx_stock_transfers_no` (`transfer_no`),
  KEY `idx_stock_transfers_status` (`status`),
  KEY `idx_stock_transfers_from` (`from_warehouse_id`),
  KEY `idx_stock_transfers_to` (`to_warehouse_id`),
  CONSTRAINT `fk_stock_transfers_from` FOREIGN KEY (`from_warehouse_id`) REFERENCES `warehouses` (`id`),
  CONSTRAINT `fk_stock_transfers_to` FOREIGN KEY (`to_warehouse_id`) REFERENCES `warehouses` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='库存调拨单';

CREATE TABLE IF NOT EXISTS `stocktake_items` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `stocktake_id` bigint unsigned NOT NULL COMMENT '盘点单ID',
  `product_id` bigint unsigned NOT NULL COMMENT '商品ID',
  `sku` varchar(64) NOT NULL COMMENT 'SKU快照',
  `product_name` varchar(128) NOT NULL COMMENT '商品名称快照',
  `expected_quantity` int NOT NULL COMMENT '账面数量（创建时快照）',
  `counted_quantity` int DEFAULT NULL COMMENT '实盘数量',
  `difference` int DEFAULT NULL COMMENT '差异 = 实盘 - 账面',
  `remark` varchar(255) DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`id`),
  KEY `idx_stocktake_items_stocktake` (`stocktake_id`),
  KEY `idx_stocktake_items_product` (`product_id`),
  CONSTRAINT `fk_stocktake_items_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`),
  CONSTRAINT `fk_stocktake_items_stocktake` FOREIGN KEY (`stocktake_id`) REFERENCES `stocktakes` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=589 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='库存盘点明细';

CREATE TABLE IF NOT EXISTS `stocktakes` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `stocktake_no` varchar(64) NOT NULL COMMENT '盘点单号',
  `status` varchar(16) NOT NULL DEFAULT 'COUNTING' COMMENT 'COUNTING/CONFIRMED/CANCELLED',
  `scope` varchar(128) DEFAULT NULL COMMENT '盘点范围描述',
  `operator` varchar(64) DEFAULT NULL COMMENT '盘点人',
  `remark` varchar(255) DEFAULT NULL COMMENT '备注',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `confirmed_at` datetime DEFAULT NULL COMMENT '确认时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `stocktake_no` (`stocktake_no`),
  KEY `idx_stocktakes_no` (`stocktake_no`),
  KEY `idx_stocktakes_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='库存盘点单';

CREATE TABLE IF NOT EXISTS `tasks` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `title` varchar(128) NOT NULL COMMENT '任务标题',
  `description` text COMMENT '任务描述',
  `status` varchar(16) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/IN_PROGRESS/DONE/CANCELLED',
  `priority` varchar(16) NOT NULL DEFAULT 'NORMAL' COMMENT 'LOW/NORMAL/HIGH/URGENT',
  `assignee` varchar(64) DEFAULT NULL COMMENT '负责人',
  `due_at` datetime DEFAULT NULL COMMENT '截止时间',
  `completed_at` datetime DEFAULT NULL COMMENT '完成时间',
  `created_by` varchar(64) DEFAULT NULL COMMENT '创建人',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_tasks_title` (`title`),
  KEY `idx_tasks_status` (`status`),
  KEY `idx_tasks_priority` (`priority`),
  KEY `idx_tasks_assignee` (`assignee`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='任务表';

CREATE TABLE IF NOT EXISTS `users` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `username` varchar(64) NOT NULL COMMENT '登录名',
  `password_hash` varchar(255) NOT NULL COMMENT 'PBKDF2 密码哈希',
  `full_name` varchar(64) DEFAULT NULL COMMENT '显示名称',
  `role` varchar(16) NOT NULL DEFAULT 'operator' COMMENT 'admin/operator/viewer',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `last_login_at` datetime DEFAULT NULL COMMENT '最近登录时间',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  KEY `idx_users_role` (`role`),
  KEY `idx_users_username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户表';

CREATE TABLE IF NOT EXISTS `warehouse_stocks` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `warehouse_id` bigint unsigned NOT NULL COMMENT '仓库ID',
  `product_id` bigint unsigned NOT NULL COMMENT '商品ID',
  `quantity` int NOT NULL DEFAULT '0' COMMENT '该仓库库存',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_warehouse_product` (`warehouse_id`,`product_id`),
  KEY `idx_warehouse_stocks_warehouse` (`warehouse_id`),
  KEY `idx_warehouse_stocks_product` (`product_id`),
  CONSTRAINT `fk_warehouse_stocks_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`),
  CONSTRAINT `fk_warehouse_stocks_warehouse` FOREIGN KEY (`warehouse_id`) REFERENCES `warehouses` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=589 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='仓库维度库存';

CREATE TABLE IF NOT EXISTS `warehouses` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(32) NOT NULL COMMENT '仓库编码',
  `name` varchar(64) NOT NULL COMMENT '仓库名称',
  `address` varchar(255) DEFAULT NULL COMMENT '仓库地址',
  `is_default` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否默认仓库',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  KEY `idx_warehouses_code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='仓库表';

-- ---------------------------------------------------------------------
-- 默认仓库（应用与调拨业务依赖它）
-- ---------------------------------------------------------------------
INSERT INTO warehouses (code, name, is_default)
SELECT 'MAIN', '主仓库', 1
WHERE NOT EXISTS (SELECT 1 FROM warehouses WHERE code = 'MAIN');

SET FOREIGN_KEY_CHECKS = 1;
