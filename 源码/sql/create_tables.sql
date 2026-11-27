-- 库存管理系统建表脚本
-- 执行方式：mysql -u root -p < create_tables.sql

CREATE DATABASE IF NOT EXISTS `库存管理系统`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `库存管理系统`;

-- 商品分类表
CREATE TABLE IF NOT EXISTS categories (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  category_name VARCHAR(32) NOT NULL UNIQUE COMMENT '分类名称',
  sku_prefix VARCHAR(8) NOT NULL UNIQUE COMMENT 'SKU前缀',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品分类表';

-- 商品表
CREATE TABLE IF NOT EXISTS products (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  category_id INT UNSIGNED NOT NULL COMMENT '商品分类ID',
  product_name VARCHAR(128) NOT NULL COMMENT '商品名称',
  sku VARCHAR(64) NOT NULL UNIQUE COMMENT '商品SKU',

  quantity INT NOT NULL DEFAULT 0 COMMENT '当前库存数量',
  price DECIMAL(10, 2) NOT NULL COMMENT '销售价格',
  cost DECIMAL(10, 2) NULL COMMENT '成本价，用于统计库存价值',

  unit VARCHAR(16) NOT NULL DEFAULT '件' COMMENT '单位',
  low_stock_threshold INT NOT NULL DEFAULT 10 COMMENT '低库存阈值',

  last_inbound_at DATETIME NULL COMMENT '最近一次入库时间',
  last_outbound_at DATETIME NULL COMMENT '最近一次出库时间',

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  CONSTRAINT fk_products_category
    FOREIGN KEY (category_id) REFERENCES categories(id),

  CONSTRAINT chk_products_quantity CHECK (quantity >= 0),
  CONSTRAINT chk_products_price CHECK (price >= 0),

  INDEX idx_product_name (product_name),
  INDEX idx_category_id (category_id),
  INDEX idx_stock (quantity, low_stock_threshold)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品表';

-- 出入库流水表
CREATE TABLE IF NOT EXISTS inventory_logs (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  product_id BIGINT UNSIGNED NOT NULL COMMENT '商品ID',
  change_type ENUM('IN', 'OUT') NOT NULL COMMENT 'IN入库 OUT出库',
  change_quantity INT NOT NULL COMMENT '变动数量',

  before_quantity INT NOT NULL COMMENT '变动前库存',
  after_quantity INT NOT NULL COMMENT '变动后库存',

  operated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
  operator VARCHAR(64) NULL COMMENT '操作人',
  remark VARCHAR(255) NULL COMMENT '备注',

  CONSTRAINT fk_logs_product
    FOREIGN KEY (product_id) REFERENCES products(id),

  CONSTRAINT chk_log_quantity CHECK (change_quantity > 0),

  INDEX idx_log_product (product_id),
  INDEX idx_log_operated_at (operated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='出入库流水表';
