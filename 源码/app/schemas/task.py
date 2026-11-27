"""任务管理 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    """新建任务请求体。"""

    title: str = Field(min_length=1, max_length=128, description="任务标题")
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="任务描述",
    )
    priority: str = Field(
        default="NORMAL",
        description="优先级：LOW / NORMAL / HIGH / URGENT",
    )
    assignee: str | None = Field(
        default=None,
        max_length=64,
        description="负责人",
    )
    due_at: datetime | None = Field(
        default=None,
        description="截止时间，ISO 8601 格式",
    )
    created_by: str | None = Field(
        default=None,
        max_length=64,
        description="创建人",
    )


class TaskUpdate(BaseModel):
    """更新任务，所有字段可选。

    未传的字段不会修改；传 null 表示清空（例如清空截止时间）。
    """

    title: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=5000)
    status: str | None = Field(
        default=None,
        description="PENDING / IN_PROGRESS / DONE / CANCELLED",
    )
    priority: str | None = Field(
        default=None,
        description="LOW / NORMAL / HIGH / URGENT",
    )
    assignee: str | None = Field(default=None, max_length=64)
    due_at: datetime | None = None


class TaskOut(BaseModel):
    """任务响应结构。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: str
    priority: str
    assignee: str | None
    due_at: datetime | None
    completed_at: datetime | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime
