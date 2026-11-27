"""任务数据访问层。"""

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models.task import Task


class TaskRepository:
    """tasks 表的数据访问对象。"""

    def __init__(self, db: Session) -> None:
        """保存数据库 Session。"""
        self.db = db

    def add(self, task: Task) -> Task:
        """新增任务并 flush 获取 ID。"""
        self.db.add(task)
        self.db.flush()
        return task

    def get_by_id(self, task_id: int) -> Task | None:
        """按主键查询任务。"""
        return self.db.get(Task, task_id)

    def delete(self, task: Task) -> None:
        """删除任务（物理删除）。"""
        self.db.delete(task)

    def list_tasks(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Task], int]:
        """分页查询任务。

        排序规则：优先级高的排前面，同优先级按创建时间倒序。
        """
        conditions = []

        if keyword:
            like_value = f"%{keyword}%"
            conditions.append(
                or_(
                    Task.title.like(like_value),
                    Task.description.like(like_value),
                )
            )
        if status:
            conditions.append(Task.status == status)
        if priority:
            conditions.append(Task.priority == priority)
        if assignee:
            conditions.append(Task.assignee == assignee)

        base_stmt = select(Task)
        if conditions:
            base_stmt = base_stmt.where(*conditions)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = int(self.db.scalar(count_stmt) or 0)

        # 用 CASE 表达式把优先级映射成数字，实现“紧急任务优先”。
        # 不直接使用 MySQL 的 FIELD()，因为单元测试跑在 SQLite 上。
        priority_order = case(
            (Task.priority == "URGENT", 0),
            (Task.priority == "HIGH", 1),
            (Task.priority == "NORMAL", 2),
            (Task.priority == "LOW", 3),
            else_=4,
        )

        items_stmt = (
            base_stmt.order_by(
                priority_order.asc(),
                Task.id.desc(),
            )
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(self.db.scalars(items_stmt).all()), total

    def count_by_status(self) -> dict[str, int]:
        """按状态统计任务数量，用于前端看板。"""
        stmt = select(Task.status, func.count(Task.id)).group_by(Task.status)
        return {status: int(count) for status, count in self.db.execute(stmt)}
