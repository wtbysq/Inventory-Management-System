"""通用 Schema。"""

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

# 泛型参数：分页数据中 items 的元素类型。
T = TypeVar("T")


class PageResponse(BaseModel, Generic[T]):
    """统一分页响应结构。

    示例:
        {
            "items": [...],
            "total": 588,
            "page": 1,
            "size": 20
        }
    """

    items: list[T]
    total: int
    page: int
    size: int


def page_response(
    items: Sequence[Any],
    total: int,
    page: int,
    size: int,
) -> dict[str, Any]:
    """构造统一的分页响应字典。

    各列表接口的返回值结构完全一致，集中在这里构造，
    避免每个控制器手写一遍键名（拼错时前端会静默拿不到数据）。
    """
    return {"items": items, "total": total, "page": page, "size": size}
