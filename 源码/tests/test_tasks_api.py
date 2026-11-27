"""任务管理接口测试。"""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient


def _create_task(client: TestClient, **overrides) -> dict:
    """创建任务的辅助函数。"""
    payload = {
        "title": "补货 FZ-0001",
        "description": "库存低于阈值，联系供应商补货",
        "priority": "HIGH",
        "assignee": "张三",
        "due_at": (datetime.now() + timedelta(days=2)).isoformat(),
    }
    payload.update(overrides)

    response = client.post("/api/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_list_tasks(client: TestClient) -> None:
    """创建任务后可以查询到，并按优先级排序。"""
    high = _create_task(client, title="高优先级任务", priority="HIGH")
    urgent = _create_task(client, title="紧急任务", priority="URGENT")

    response = client.get("/api/tasks", params={"page": 1, "size": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    # 紧急任务应排在高优先级前面。
    assert data["items"][0]["id"] == urgent["id"]
    assert data["items"][1]["id"] == high["id"]
    # 创建人默认取当前登录用户。
    assert high["created_by"] == "admin"
    assert high["status"] == "PENDING"


def test_filter_tasks_by_status_and_assignee(client: TestClient) -> None:
    """支持按状态、负责人筛选。"""
    task = _create_task(client, assignee="李四")
    _create_task(client, title="另一个任务", assignee="王五")

    response = client.get(
        "/api/tasks",
        params={"status": "PENDING", "assignee": "李四"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == task["id"]


def test_update_task_to_done_sets_completed_at(client: TestClient) -> None:
    """状态改为 DONE 时自动记录完成时间。"""
    task = _create_task(client)

    response = client.patch(
        f"/api/tasks/{task['id']}",
        json={"status": "DONE"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "DONE"
    assert data["completed_at"] is not None


def test_update_task_with_invalid_priority(client: TestClient) -> None:
    """非法优先级返回 422。"""
    task = _create_task(client)

    response = client.patch(
        f"/api/tasks/{task['id']}",
        json={"priority": "SUPER_URGENT"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_delete_task_requires_cancelled_status(client: TestClient) -> None:
    """未取消的任务不允许删除，取消后可以删除。"""
    task = _create_task(client)

    blocked = client.delete(f"/api/tasks/{task['id']}")
    assert blocked.status_code == 409

    cancelled = client.patch(
        f"/api/tasks/{task['id']}",
        json={"status": "CANCELLED"},
    )
    assert cancelled.status_code == 200

    deleted = client.delete(f"/api/tasks/{task['id']}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/tasks/{task['id']}")
    assert missing.status_code == 404


def test_task_stats(client: TestClient) -> None:
    """任务状态统计应包含所有状态，未出现的补 0。"""
    task = _create_task(client)
    client.patch(f"/api/tasks/{task['id']}", json={"status": "DONE"})

    response = client.get("/api/tasks/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["DONE"] == 1
    assert data["PENDING"] == 0
    assert data["IN_PROGRESS"] == 0
    assert data["CANCELLED"] == 0
