"""初始表结构：商品、库存、订单、退货、用户、任务、盘点、调拨。

Revision ID: 0001
Revises: 无
Create Date: 2026-11-23

适用场景:
    - 全新数据库：直接 `alembic upgrade head`。
    - 已经用 sql/create_tables.sql 建过旧表：
        1. 执行 sql/upgrade_v2.sql 补齐新表和字段；
        2. 执行 `alembic stamp 0001` 把版本标记为最新，
           不要再次 upgrade，否则会重复建表。

注意:
    本迁移使用了 MySQL 方言的 BIGINT UNSIGNED，
    因为 products.id / orders.id 在旧库中就是无符号大整数，
    外键两边类型必须完全一致。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 无符号大整数，与 products.id / orders.id 保持一致。
UBIGINT = mysql.BIGINT(unsigned=True)


def upgrade() -> None:
    """创建全部业务表。"""

    # ------------------------------------------------------------------
    # 1. 分类
    # ------------------------------------------------------------------
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category_name", sa.String(length=32), nullable=False),
        sa.Column("sku_prefix", sa.String(length=8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_name"),
        sa.UniqueConstraint("sku_prefix"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 2. 商品
    # ------------------------------------------------------------------
    op.create_table(
        "products",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=128), nullable=False, index=True),
        sa.Column("sku", sa.String(length=64), nullable=False, index=True),
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("cost", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column(
            "unit",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'件'"),
        ),
        sa.Column(
            "low_stock_threshold",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("10"),
        ),
        sa.Column("last_inbound_at", sa.DateTime(), nullable=True),
        sa.Column("last_outbound_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_products_category",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 3. 库存流水
    # ------------------------------------------------------------------
    op.create_table(
        "inventory_logs",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("product_id", UBIGINT, nullable=False, index=True),
        sa.Column("change_type", sa.String(length=16), nullable=False, index=True),
        sa.Column("change_quantity", sa.Integer(), nullable=False),
        sa.Column("before_quantity", sa.Integer(), nullable=False),
        sa.Column("after_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "operated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            index=True,
        ),
        sa.Column("operator", sa.String(length=64), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_logs_product",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 4. 订单
    # ------------------------------------------------------------------
    op.create_table(
        "orders",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("order_no", sa.String(length=64), nullable=False, index=True),
        sa.Column(
            "total_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'CREATED'"),
            index=True,
        ),
        sa.Column("operator", sa.String(length=64), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("payment_method", sa.String(length=32), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=255), nullable=True),
        sa.Column(
            "refunded_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_no"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 5. 订单明细
    # ------------------------------------------------------------------
    op.create_table(
        "order_items",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("order_id", UBIGINT, nullable=False, index=True),
        sa.Column("product_id", UBIGINT, nullable=False, index=True),
        sa.Column("product_name", sa.String(length=128), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "returned_quantity",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_order_items_order",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_order_items_product",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 6. 退货单
    # ------------------------------------------------------------------
    op.create_table(
        "order_returns",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("return_no", sa.String(length=64), nullable=False, index=True),
        sa.Column("order_id", UBIGINT, nullable=False, index=True),
        sa.Column(
            "refund_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("operator", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_order_returns_order",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("return_no"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 7. 退货明细
    # ------------------------------------------------------------------
    op.create_table(
        "order_return_items",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("return_id", UBIGINT, nullable=False, index=True),
        sa.Column("order_item_id", UBIGINT, nullable=False, index=True),
        sa.Column("product_id", UBIGINT, nullable=False, index=True),
        sa.Column("product_name", sa.String(length=128), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.ForeignKeyConstraint(
            ["return_id"],
            ["order_returns.id"],
            name="fk_return_items_return",
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"],
            ["order_items.id"],
            name="fk_return_items_order_item",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_return_items_product",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 8. 用户
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False, index=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=64), nullable=True),
        sa.Column(
            "role",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'operator'"),
            index=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 9. 任务
    # ------------------------------------------------------------------
    op.create_table(
        "tasks",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'PENDING'"),
            index=True,
        ),
        sa.Column(
            "priority",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'NORMAL'"),
            index=True,
        ),
        sa.Column("assignee", sa.String(length=64), nullable=True, index=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 10. 仓库
    # ------------------------------------------------------------------
    op.create_table(
        "warehouses",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False, index=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 11. 仓库库存
    # ------------------------------------------------------------------
    op.create_table(
        "warehouse_stocks",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("warehouse_id", UBIGINT, nullable=False, index=True),
        sa.Column("product_id", UBIGINT, nullable=False, index=True),
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_warehouse_stocks_warehouse",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_warehouse_stocks_product",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "warehouse_id",
            "product_id",
            name="uk_warehouse_product",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 12. 盘点单
    # ------------------------------------------------------------------
    op.create_table(
        "stocktakes",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("stocktake_no", sa.String(length=64), nullable=False, index=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'COUNTING'"),
            index=True,
        ),
        sa.Column("scope", sa.String(length=128), nullable=True),
        sa.Column("operator", sa.String(length=64), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stocktake_no"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 13. 盘点明细
    # ------------------------------------------------------------------
    op.create_table(
        "stocktake_items",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("stocktake_id", UBIGINT, nullable=False, index=True),
        sa.Column("product_id", UBIGINT, nullable=False, index=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=128), nullable=False),
        sa.Column("expected_quantity", sa.Integer(), nullable=False),
        sa.Column("counted_quantity", sa.Integer(), nullable=True),
        sa.Column("difference", sa.Integer(), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["stocktake_id"],
            ["stocktakes.id"],
            name="fk_stocktake_items_stocktake",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_stocktake_items_product",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 14. 调拨单
    # ------------------------------------------------------------------
    op.create_table(
        "stock_transfers",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("transfer_no", sa.String(length=64), nullable=False, index=True),
        sa.Column("from_warehouse_id", UBIGINT, nullable=False, index=True),
        sa.Column("to_warehouse_id", UBIGINT, nullable=False, index=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'COMPLETED'"),
            index=True,
        ),
        sa.Column("operator", sa.String(length=64), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["from_warehouse_id"],
            ["warehouses.id"],
            name="fk_stock_transfers_from",
        ),
        sa.ForeignKeyConstraint(
            ["to_warehouse_id"],
            ["warehouses.id"],
            name="fk_stock_transfers_to",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transfer_no"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 15. 调拨明细
    # ------------------------------------------------------------------
    op.create_table(
        "stock_transfer_items",
        sa.Column("id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("transfer_id", UBIGINT, nullable=False, index=True),
        sa.Column("product_id", UBIGINT, nullable=False, index=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=128), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["transfer_id"],
            ["stock_transfers.id"],
            name="fk_transfer_items_transfer",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_transfer_items_product",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # ------------------------------------------------------------------
    # 16. 默认仓库初始数据
    # ------------------------------------------------------------------
    op.execute(
        "INSERT INTO warehouses (code, name, is_default) "
        "VALUES ('MAIN', '主仓库', 1)"
    )


def downgrade() -> None:
    """按外键依赖的反序删除全部表。"""
    op.drop_table("stock_transfer_items")
    op.drop_table("stock_transfers")
    op.drop_table("stocktake_items")
    op.drop_table("stocktakes")
    op.drop_table("warehouse_stocks")
    op.drop_table("warehouses")
    op.drop_table("tasks")
    op.drop_table("users")
    op.drop_table("order_return_items")
    op.drop_table("order_returns")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("inventory_logs")
    op.drop_table("products")
    op.drop_table("categories")
