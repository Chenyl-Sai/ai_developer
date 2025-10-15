"""
统一管理LangGraph人工介入中断
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ..utils.logger import agent_logger
from ai_dev.core.global_state import GlobalState


class InterruptionHandler(ABC):

    @abstractmethod
    async def handle(self, interrupt_info, **kwargs):
        pass


class PermissionInterruptionHandler(InterruptionHandler):
    """权限授权中断处理"""

    async def handle(self, interrupt_info, **kwargs):
        """处理权限请求中断
                Args:
                    interrupt_info: 权限请求数据
                """
        # 获取CLI实例并判断类型
        cli_instance = GlobalState.get_cli_instance()
        agent_logger.info(f"[PERMISSION_DEBUG] Agent {interrupt_info}")

        # 使用AdvancedCLI的动态输入域切换
        from ai_dev.permission.permission_ui import PermissionUI
        permission_ui = PermissionUI(cli_instance)
        permission_ui.display_permission_request(interrupt_info)


class WaitInputInterruptionHandler(InterruptionHandler):
    """等待用户输入开启下一轮对话处理"""

    async def handle(self, interrupt_info, **kwargs):
        """什么都不用做，等着就行了"""
        pass


class InterruptionManager:
    """统一管理LangGraph人工介入中断"""

    def __init__(self):
        self.interruption_handlers: Dict[str, InterruptionHandler] = {}
        self._register_default_handlers()

    def _register_default_handlers(self):
        """注册默认中断处理器"""
        self.register_handler("permission_request", PermissionInterruptionHandler())
        self.register_handler("wait_input", WaitInputInterruptionHandler())

    def register_handler(self, interruption_type: str, handler: InterruptionHandler):
        """注册中断处理器

        Args:
            interruption_type: 中断类型
            handler: 处理函数，接受(data, assistant)参数，返回恢复值
        """
        self.interruption_handlers[interruption_type] = handler
        agent_logger.debug(f"注册中断处理器: {interruption_type}")

    async def handle_interruption(self, interruption_type: str, interrupt_info: Dict[str, Any]) -> Optional[str]:
        """处理中断并返回恢复值

        Args:
            interruption_type: 中断类型
            interrupt_info: 中断数据

        Returns:
            恢复执行所需的值，如用户选择
        """
        handler = self.interruption_handlers.get(interruption_type)
        agent_logger.info(f"处理中断: {interruption_type}")
        await handler.handle(interrupt_info)

    def is_interruption_chunk(self, chunk: Dict[str, Any]) -> bool:
        """判断是否为中断chunk

        Args:
            chunk: 流式输出块

        Returns:
            是否为中断
        """
        return chunk.get("type") in self.interruption_handlers
