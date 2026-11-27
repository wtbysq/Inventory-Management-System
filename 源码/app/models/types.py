"""模型层公共类型定义。"""

from sqlalchemy import BigInteger, Integer
from sqlalchemy.dialects.mysql import BIGINT as MySQLBIGINT

# MySQL 中商品主键使用 BIGINT。
# SQLite 单元测试中 BIGINT 主键无法像 INTEGER PRIMARY KEY 那样自增，
# 因此通过 with_variant 在 SQLite 方言下自动降级为 INTEGER。
BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")

# 订单表是后建的表，需要和现有 products.id 的 BIGINT UNSIGNED 保持一致，
# 否则 MySQL 创建外键时会因为 signed / unsigned 不一致而失败。
BIGINT_UNSIGNED_ID = MySQLBIGINT(unsigned=True).with_variant(
    Integer,
    "sqlite",
)
