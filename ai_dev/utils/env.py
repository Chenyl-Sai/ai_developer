import os
import sys
import asyncio
import socket
from pathlib import Path

# -------------------------
# 是否在 Docker 中
# -------------------------
async def get_is_docker() -> bool:
    """
    检查当前是否运行在 Docker 容器环境中
    
    通过检测 /.dockerenv 文件是否存在以及当前平台是否为 Linux 来判断
    
    Returns:
        bool: 如果运行在 Docker 容器中返回 True，否则返回 False
    """
    dockerenv = Path("/.dockerenv")
    return dockerenv.exists() and sys.platform.startswith("linux")


# -------------------------
# 是否有网络访问
# -------------------------
async def has_internet_access(timeout: float = 1.0) -> bool:
    """
    检查当前是否有互联网访问权限
    
    通过尝试连接 Cloudflare DNS 服务器 (1.1.1.1:80) 来测试网络连通性
    类似于 JavaScript 中的 fetch('http://1.1.1.1', {method: 'HEAD'})
    
    Args:
        timeout (float): 连接超时时间，默认为 1.0 秒
        
    Returns:
        bool: 如果能够成功连接返回 True，否则返回 False
    """
    try:
        loop = asyncio.get_running_loop()
        fut = loop.getaddrinfo("1.1.1.1", 80, family=socket.AF_INET)

        # 等待 DNS 解析 & 连接
        await asyncio.wait_for(fut, timeout=timeout)

        with socket.create_connection(("1.1.1.1", 80), timeout=timeout):
            return True
    except Exception:
        return False


# -------------------------
# 环境信息
# -------------------------
env = {
    "getIsDocker": get_is_docker,
    "hasInternetAccess": has_internet_access,
    "isCI": bool(os.getenv("CI")),
    "platform": (
        "windows"
        if sys.platform.startswith("win")
        else "macos"
        if sys.platform == "darwin"
        else "linux"
    ),
    "pythonVersion": sys.version,
    "terminal": os.getenv("TERM_PROGRAM"),
}
