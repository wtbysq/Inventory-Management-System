"""任务管理 ORM 模型。

任务模块用于给仓库/运营团队派活，例如：
    - “补货：FZ-0001 库存低于阈值”
    - “盘点本周新到的货”
    - “核对订单 SO20261123xxxx 的退货”

任务不属于任何订单的强关联，保持通用，便于后续扩展。
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import BIGINT_UNSIGNED_ID

# 任务状态常量。用字符串而不是 Python Enum，
# 便于数据库直接查看，也方便前端按字符串筛选。
TASK_STATUS_PENDING = "PENDING"
TASK_STATUS_IN_PROGRESS = "IN_PROGRESS"
TASK_STATUS_DONE = "DONE"
TASK_STATUS_CANCELLED = "CANCELLED"

TASK_STATUSES: tuple[str, ...] = (
    TASK_STATUS_PENDING,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_DONE,
    TASK_STATUS_CANCELLED,
)

TASK_STATUS_LABELS: dict[str, str] = {
    TASK_STATUS_PENDING: "待处理",
    TASK_STATUS_IN_PROGRESS: "进行中",
    TASK_STATUS_DONE: "已完成",
    TASK_STATUS_CANCELLED: "已取消",
}

# 优先级常量，数值越大越紧急。
TASK_PRIORITIES: tuple[str, ...] = ("LOW", "NORMAL", "HIGH", "URGENT")

TASK_PRIORITY_LABELS: dict[str, str] = {
    "LOW": "低",
    "NORMAL": "普通",
    "HIGH": "高",
    "URGENT": "紧急",
}


class Task(Base):
    """对应数据库表 tasks。"""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(
        BIGINT_UNSIGNED_ID,
        primary_key=True,
        autoincrement=True,
        comment="任务ID",
    )
    title: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="任务标题",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="任务详细描述",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=TASK_STATUS_PENDING,
        index=True,
        comment="PENDING / IN_PROGRESS / DONE / CANCELLED",
    )
    priority: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="NORMAL",
        index=True,
        comment="LOW / NORMAL / HIGH / URGENT",
    )
    assignee: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="负责人",
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="截止时间",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="完成时间，状态变为 DONE 时自动写入",
    )
    created_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="创建人",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )

    def __repr__(self) -> str:
        """方便调试时查看对象内容。"""
        return (
            f"<Task id={self.id} title={self.title!r} "
            f"status={self.status} priority={self.priority}>"
        )
