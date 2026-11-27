"""任务管理业务逻辑。"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.task import (
    TASK_PRIORITIES,
    TASK_PRIORITY_LABELS,
    TASK_STATUS_DONE,
    TASK_STATUS_LABELS,
    TASK_STATUSES,
    Task,
)
from app.repositories.task_repo import TaskRepository


class TaskService:
    """任务的增删改查与状态流转。"""

    def __init__(self, db: Session) -> None:
        """初始化任务 Service。"""
        self.db = db
        self.task_repo = TaskRepository(db)

    def create_task(
        self,
        *,
        title: str,
        description: str | None = None,
        priority: str = "NORMAL",
        assignee: str | None = None,
        due_at: datetime | None = None,
        created_by: str | None = None,
    ) -> Task:
        """创建任务。"""
        title = title.strip()
        if not title:
            raise ValidationError("任务标题不能为空")

        self._validate_priority(priority)

        task = Task(
            title=title,
            description=description,
            status="PENDING",
            priority=priority,
            assignee=assignee,
            due_at=due_at,
            created_by=created_by,
        )
        self.task_repo.add(task)
        self.db.commit()
        return task

    def get_task(self, task_id: int) -> Task:
        """查询任务详情。"""
        task = self.task_repo.get_by_id(task_id)
        if task is None:
            raise NotFoundError(f"任务不存在: id={task_id}")
        return task

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
        """分页查询任务。"""
        if status:
            self._validate_status(status)
        if priority:
            self._validate_priority(priority)

        return self.task_repo.list_tasks(
            keyword=keyword,
            status=status,
            priority=priority,
            assignee=assignee,
            page=page,
            size=size,
        )

    def update_task(self, task_id: int, *, changes: dict) -> Task:
        """部分更新任务。

        状态变为 DONE 时自动填写完成时间；
        从 DONE 改回其他状态时清空完成时间。
        """
        task = self.get_task(task_id)

        if "title" in changes and changes["title"] is not None:
            title = str(changes["title"]).strip()
            if not title:
                raise ValidationError("任务标题不能为空")
            task.title = title

        if "description" in changes:
            task.description = changes["description"]

        if "priority" in changes and changes["priority"] is not None:
            priority = str(changes["priority"])
            self._validate_priority(priority)
            task.priority = priority

        if "assignee" in changes:
            task.assignee = changes["assignee"]

        if "due_at" in changes:
            task.due_at = changes["due_at"]

        if "status" in changes and changes["status"] is not None:
            status = str(changes["status"])
            self._validate_status(status)

            if status == TASK_STATUS_DONE and task.completed_at is None:
                task.completed_at = datetime.now()
            elif status != TASK_STATUS_DONE:
                task.completed_at = None

            task.status = status

        self.db.commit()
        return task

    def delete_task(self, task_id: int) -> None:
        """删除任务。

        已取消的任务才允许删除，避免误删正在进行的工作记录。
        如果确实要删除，先把状态改为 CANCELLED。
        """
        task = self.get_task(task_id)

        if task.status != "CANCELLED":
            raise ConflictError("只有已取消的任务可以删除，请先取消任务")

        self.task_repo.delete(task)
        self.db.commit()

    def count_by_status(self) -> dict[str, int]:
        """按状态统计任务数量，未出现的状态补 0。"""
        counts = self.task_repo.count_by_status()
        return {status: counts.get(status, 0) for status in TASK_STATUSES}

    # ------------------------------------------------------------------
    # 校验辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_status(status: str) -> None:
        """校验任务状态。"""
        if status not in TASK_STATUSES:
            allowed = " / ".join(
                f"{value}({TASK_STATUS_LABELS[value]})"
                for value in TASK_STATUSES
            )
            raise ValidationError(f"任务状态不合法: {status}，可选：{allowed}")

    @staticmethod
    def _validate_priority(priority: str) -> None:
        """校验任务优先级。"""
        if priority not in TASK_PRIORITIES:
            allowed = " / ".join(
                f"{value}({TASK_PRIORITY_LABELS[value]})"
                for value in TASK_PRIORITIES
            )
            raise ValidationError(f"任务优先级不合法: {priority}，可选：{allowed}")
