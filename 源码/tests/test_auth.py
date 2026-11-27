"""登录与权限控制测试。"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    ROLE_VIEWER,
    get_current_user,
    hash_password,
    verify_password,
)
from app.main import app
from app.models.user import User


def test_login_success(
    client: TestClient,
    db_session: Session,
) -> None:
    """正确用户名密码应返回 token 和用户信息。"""
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert data["access_token"].count(".") == 2
    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "admin"
    # 响应中绝不能出现密码哈希。
    assert "password_hash" not in data["user"]

    db_session.refresh(db_session.get(User, 1))
    assert db_session.get(User, 1).last_login_at is not None


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    """密码错误返回 401，且不区分用户名是否存在。"""
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_request_without_token_returns_401(
    anonymous_client: TestClient,
) -> None:
    """未登录访问业务接口应返回 401。"""
    response = anonymous_client.get("/api/products")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_frontend_login_flow(
    anonymous_client: TestClient,
    db_session: Session,
) -> None:
    """真实登录拿 token，再带着 token 访问受保护接口。"""
    login_response = anonymous_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = login_response.json()["access_token"]

    me_response = anonymous_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "admin"

    products_response = anonymous_client.get(
        "/api/products",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert products_response.status_code == 200


def test_invalid_token_returns_401(anonymous_client: TestClient) -> None:
    """伪造的 token 应被签名校验拦截。"""
    response = anonymous_client.get(
        "/api/products",
        headers={"Authorization": "Bearer fake.token.value"},
    )

    assert response.status_code == 401


def test_viewer_cannot_write(
    client: TestClient,
    viewer_user: User,
    sample_product,
) -> None:
    """只读用户可以查询，但入库应返回 403。"""
    app.dependency_overrides[get_current_user] = lambda: viewer_user

    read_response = client.get("/api/products")
    assert read_response.status_code == 200

    write_response = client.post(
        "/api/inventory/inbound",
        json={"product_id": sample_product.id, "quantity": 1},
    )
    assert write_response.status_code == 403
    assert write_response.json()["code"] == "FORBIDDEN"


def test_admin_can_create_user(client: TestClient) -> None:
    """管理员可以创建用户，重复登录名返回 409。"""
    payload = {
        "username": "operator1",
        "password": "operator123",
        "full_name": "仓库操作员",
        "role": "operator",
    }

    response = client.post("/api/users", json=payload)
    assert response.status_code == 201
    assert response.json()["username"] == "operator1"
    assert response.json()["role"] == "operator"

    duplicate = client.post("/api/users", json=payload)
    assert duplicate.status_code == 409


def test_cannot_demote_last_admin(
    client: TestClient,
    admin_user: User,
) -> None:
    """系统必须保留至少一个启用的管理员。"""
    response = client.patch(
        f"/api/users/{admin_user.id}",
        json={"role": ROLE_VIEWER},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


def test_change_password_and_login_with_new_password(
    client: TestClient,
    admin_user: User,
) -> None:
    """修改密码后旧密码失效、新密码可以登录。"""
    response = client.post(
        "/api/auth/change-password",
        json={"old_password": "admin123", "new_password": "newpass123"},
    )
    assert response.status_code == 200

    # 移除默认登录，验证真实登录流程。
    app.dependency_overrides.pop(get_current_user, None)
    settings.rate_limit_enabled = False

    old_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "newpass123"},
    )
    assert new_login.status_code == 200


def test_password_hash_and_verify(db_session: Session) -> None:
    """密码哈希不保存明文，且校验函数能正确识别密码。"""
    hashed = hash_password("secret123")

    assert hashed.startswith("pbkdf2_sha256$")
    assert "secret123" not in hashed
    assert verify_password("secret123", hashed) is True
    assert verify_password("wrong-password", hashed) is False
    assert verify_password("secret123", None) is False
