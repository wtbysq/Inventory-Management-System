"""库存管理系统桌面启动器。

双击 exe 后：
1. 切换到 exe 所在目录，读取同目录的 .env
2. 启动 FastAPI / Uvicorn
3. 自动打开浏览器访问 Swagger

注意：
    这是后端服务的启动器，不是带界面的桌面客户端。
    MySQL 仍然需要在本机运行。
"""

from __future__ import annotations

import multiprocessing
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def get_base_dir() -> Path:
    """获取程序所在目录。

    - 源码运行时：项目根目录
    - PyInstaller 打包后：exe 所在目录
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# 必须在导入 app.db 之前切换工作目录，
# 这样 pydantic-settings 才能读取 exe 同目录的 .env。
BASE_DIR = get_base_dir()
os.chdir(BASE_DIR)

# noqa: E402 表示这里故意在修改工作目录后再导入。
from app.main import app  # noqa: E402

import uvicorn  # noqa: E402


def find_free_port(preferred: int = 8000) -> int:
    """从 preferred 开始查找一个可用端口。

    如果 8000 被占用，会自动尝试 8001、8002……
    """
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue

    raise RuntimeError("8000-8019 端口都被占用，无法启动服务")


def open_browser_later(url: str, delay: float = 1.5) -> None:
    """延迟打开浏览器，给 Uvicorn 一点启动时间。"""

    def _open() -> None:
        time.sleep(delay)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


def main() -> None:
    """启动 FastAPI 服务。"""
    port = find_free_port()
    app_url = f"http://127.0.0.1:{port}/"
    docs_url = f"http://127.0.0.1:{port}/docs"

    print("=" * 64)
    print("库存管理系统")
    print(f"管理页面: {app_url}")
    print(f"Swagger 文档: {docs_url}")
    print(f"工作目录: {BASE_DIR}")
    print("关闭窗口或按 Ctrl+C 停止服务")
    print("=" * 64)

    # 测试或服务器环境可以不自动打开浏览器：
    # InventoryManager.exe --no-browser
    if "--no-browser" not in sys.argv:
        open_browser_later(app_url)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        main()
    except KeyboardInterrupt:
        print("\n服务已停止")
    except Exception as exc:
        print(f"\n启动失败: {exc}")
        input("按回车键退出...")
