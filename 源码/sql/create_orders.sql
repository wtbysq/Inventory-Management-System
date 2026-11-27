-- 订单模块建表脚本
-- 先执行 create_tables.sql，确保 categories、products 已存在
-- 执行：mysql --default-character-set=utf8mb4 -u root -p < create_orders.sql

USE `库存管理系统`;

-- 订单主表
CREATE TABLE IF NOT EXISTS orders (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_no VARCHAR(64) NOT NULL UNIQUE COMMENT '订单号',
  total_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '订单总金额',
  status VARCHAR(16) NOT NULL DEFAULT 'CREATED' COMMENT 'CREATED/PAID/CANCELLED',
  operator VARCHAR(64) NULL COMMENT '下单人',
  remark VARCHAR(255) NULL COMMENT '订单备注',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  INDEX idx_orders_status (status),
  INDEX idx_orders_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表';

-- 订单明细表
CREATE TABLE IF NOT EXISTS order_items (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT UNSIGNED NOT NULL COMMENT '订单ID',
  product_id BIGINT UNSIGNED NOT NULL COMMENT '商品ID',

  product_name VARCHAR(128) NOT NULL COMMENT '下单时的商品名称',
  sku VARCHAR(64) NOT NULL COMMENT '下单时的商品SKU',
  quantity INT NOT NULL COMMENT '购买数量',
  unit_price DECIMAL(10, 2) NOT NULL COMMENT '下单时的单价',
  subtotal DECIMAL(12, 2) NOT NULL COMMENT '小计金额',

  CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id) REFERENCES orders(id),
  CONSTRAINT fk_order_items_product
    FOREIGN KEY (product_id) REFERENCES products(id),
  CONSTRAINT chk_order_items_quantity CHECK (quantity > 0),

  INDEX idx_order_items_order (order_id),
  INDEX idx_order_items_product (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单明细表';
