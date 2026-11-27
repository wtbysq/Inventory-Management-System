"""任务管理接口。"""

from fastapi import APIRouter, Depends, Path, Query, Response

from app.core.security import CurrentUser, require_login, require_operator
from app.dependencies import get_task_service
from app.schemas.common import PageResponse, page_response
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["任务管理"])


@router.get(
    "/stats",
    response_model=dict[str, int],
    summary="任务状态统计",
    description="返回各状态的任务数量，用于看板展示。",
    dependencies=[Depends(require_login)],
)
def task_stats(service: TaskService = Depends(get_task_service)):
    """按状态统计任务数量。"""
    return service.count_by_status()


@router.get(
    "",
    response_model=PageResponse[TaskOut],
    summary="分页查询任务",
    description="支持关键字、状态、优先级、负责人筛选。",
    dependencies=[Depends(require_login)],
)
def list_tasks(
    keyword: str | None = Query(
        default=None,
        description="标题或描述模糊搜索",
    ),
    status: str | None = Query(
        default=None,
        description="PENDING / IN_PROGRESS / DONE / CANCELLED",
    ),
    priority: str | None = Query(
        default=None,
        description="LOW / NORMAL / HIGH / URGENT",
    ),
    assignee: str | None = Query(default=None, description="负责人"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    service: TaskService = Depends(get_task_service),
):
    """分页查询任务。"""
    items, total = service.list_tasks(
        keyword=keyword,
        status=status,
        priority=priority,
        assignee=assignee,
        page=page,
        size=size,
    )
    return page_response(items, total, page, size)


@router.post(
    "",
    response_model=TaskOut,
    status_code=201,
    summary="创建任务",
    description="操作员和管理员可以创建任务。",
    dependencies=[Depends(require_operator)],
)
def create_task(
    payload: TaskCreate,
    current_user: CurrentUser,
    service: TaskService = Depends(get_task_service),
):
    """创建任务，创建人默认取当前登录用户。"""
    return service.create_task(
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        assignee=payload.assignee,
        due_at=payload.due_at,
        created_by=payload.created_by or current_user.username,
    )


@router.get(
    "/{task_id}",
    response_model=TaskOut,
    summary="任务详情",
    dependencies=[Depends(require_login)],
)
def get_task(
    task_id: int = Path(ge=1, description="任务 ID"),
    service: TaskService = Depends(get_task_service),
):
    """查询任务详情。"""
    return service.get_task(task_id)


@router.patch(
    "/{task_id}",
    response_model=TaskOut,
    summary="更新任务",
    description=(
        "支持修改标题、描述、状态、优先级、负责人和截止时间。\n\n"
        "状态改为 DONE 时自动记录完成时间。"
    ),
    dependencies=[Depends(require_operator)],
)
def update_task(
    payload: TaskUpdate,
    task_id: int = Path(ge=1, description="任务 ID"),
    service: TaskService = Depends(get_task_service),
):
    """局部更新任务。"""
    return service.update_task(
        task_id,
        changes=payload.model_dump(exclude_unset=True),
    )


@router.delete(
    "/{task_id}",
    status_code=204,
    summary="删除任务",
    description="只有已取消（CANCELLED）的任务可以删除。",
    dependencies=[Depends(require_operator)],
)
def delete_task(
    task_id: int = Path(ge=1, description="任务 ID"),
    service: TaskService = Depends(get_task_service),
):
    """删除已取消的任务。"""
    service.delete_task(task_id)
    return Response(status_code=204)
