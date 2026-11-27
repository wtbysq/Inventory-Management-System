"""登录、密码哈希与 JWT 鉴权。

设计要点:
1. 密码只保存 PBKDF2-SHA256 哈希，绝不保存明文。
   - 使用 Python 标准库 `hashlib.pbkdf2_hmac`，不需要额外安装 bcrypt。
   - 每个用户使用独立随机盐，防止彩虹表。
2. 登录成功后签发 JWT（HS256）。
   - 使用标准库 `hmac` + `base64url` 手写实现，避免引入 PyJWT 依赖。
   - payload 中只放用户 ID、用户名、角色和过期时间，不放敏感信息。
3. `get_current_user` 作为 FastAPI 依赖，负责解析 Authorization 请求头。
4. `require_roles` 是权限依赖工厂，用法: `Depends(require_roles(ROLE_ADMIN))`。

角色说明:
    admin    管理员：所有功能 + 用户管理
    operator 操作员：商品、库存、订单、盘点、调拨、任务的读写
    viewer   只读用户：只能查询，不能修改任何数据
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.db import get_db
from app.models.user import User

# ----------------------------------------------------------------------
# 角色常量
# ----------------------------------------------------------------------
ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
ROLE_VIEWER = "viewer"

# 角色 -> 中文名，返回给前端展示。
ROLE_LABELS: dict[str, str] = {
    ROLE_ADMIN: "管理员",
    ROLE_OPERATOR: "操作员",
    ROLE_VIEWER: "只读用户",
}

ALL_ROLES = (ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)


# ----------------------------------------------------------------------
# 密码哈希
# ----------------------------------------------------------------------
def hash_password(password: str) -> str:
    """把明文密码转换成可入库的哈希字符串。

    存储格式:
        pbkdf2_sha256$迭代次数$盐(hex)$哈希(hex)

    使用固定格式而不是直接存哈希，是为了以后更换算法时可以平滑升级。
    """
    salt = secrets.token_bytes(16)
    iterations = settings.password_hash_iterations
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    """校验明文密码是否与数据库中的哈希匹配。

    任何格式错误都返回 False，不向调用方泄露细节。
    """
    if not stored_hash:
        return False

    try:
        algorithm, iterations_text, salt_hex, digest_hex = stored_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False

        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        # 使用 compare_digest 做常量时间比较，避免时序攻击。
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# ----------------------------------------------------------------------
# JWT（HS256）编解码
# ----------------------------------------------------------------------
def _b64url_encode(data: bytes) -> str:
    """base64url 编码，去掉末尾的 = 填充（JWT 规范要求）。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    """base64url 解码，自动补齐 = 填充。"""
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(message: str) -> str:
    """用 SECRET_KEY 对 message 做 HMAC-SHA256 签名。"""
    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        message.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(signature)


def create_access_token(
    *,
    user_id: int,
    username: str,
    role: str,
    expires_minutes: int | None = None,
) -> tuple[str, int]:
    """签发 access token。

    Returns:
        (token, 有效期秒数)
    """
    now = int(time.time())
    minutes = expires_minutes or settings.access_token_expire_minutes
    expires_in = minutes * 60

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + expires_in,
    }

    segments = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":")).encode()),
            _b64url_encode(
                json.dumps(
                    payload,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode()
            ),
        ]
    )
    return f"{segments}.{_sign(segments)}", expires_in


def decode_access_token(token: str) -> dict:
    """校验并解析 token。

    Raises:
        UnauthorizedError: token 格式错误、签名不正确或已过期。
    """
    try:
        header_text, payload_text, signature = token.split(".")
    except ValueError as exc:
        raise UnauthorizedError("登录凭证格式错误，请重新登录") from exc

    signing_input = f"{header_text}.{payload_text}"
    if not hmac.compare_digest(signature, _sign(signing_input)):
        raise UnauthorizedError("登录凭证签名校验失败，请重新登录")

    try:
        payload = json.loads(_b64url_decode(payload_text))
    except (ValueError, TypeError) as exc:
        raise UnauthorizedError("登录凭证内容无法解析，请重新登录") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise UnauthorizedError("登录已过期，请重新登录")

    return payload


# ----------------------------------------------------------------------
# FastAPI 依赖
# ----------------------------------------------------------------------
def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """从 Authorization: Bearer <token> 中解析当前登录用户。

    注意:
        - 未携带 token 返回 401。
        - token 有效但用户被禁用返回 403。
    """
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")

    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError("请先登录后再访问该接口")

    payload = decode_access_token(token.strip())

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("登录凭证缺少用户信息，请重新登录") from exc

    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("登录用户不存在，请重新登录")
    if not user.is_active:
        raise ForbiddenError("账号已被禁用，请联系管理员")

    return user


# 便于在 Controller 中写 `user: CurrentUser` 的类型别名。
CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str) -> Callable[..., User]:
    """生成权限校验依赖。

    用法:
        @router.post("", dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_OPERATOR))])
        def create(...): ...

    这样 Controller 不需要写 if 判断，权限逻辑集中在依赖中。
    """

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            allowed = "/".join(ROLE_LABELS.get(role, role) for role in roles)
            raise ForbiddenError(
                f"当前角色（{ROLE_LABELS.get(current_user.role, current_user.role)}）"
                f"没有该操作权限，需要：{allowed}"
            )
        return current_user

    return dependency


# 常用组合，避免每个 Controller 重复写。
require_login = require_roles(*ALL_ROLES)
require_operator = require_roles(ROLE_ADMIN, ROLE_OPERATOR)
require_admin = require_roles(ROLE_ADMIN)
