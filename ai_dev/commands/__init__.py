"""
指令系统模块
"""

from typing import Dict, Type, Optional
from abc import ABC, abstractmethod


class Command(ABC):
    """指令基类"""

    @abstractmethod
    def execute(self, cli, args: str) -> bool:
        """
        执行指令

        Args:
            cli: CLI实例
            args: 指令参数

        Returns:
            bool: 是否继续运行程序
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """指令描述"""
        pass


class CommandRegistry:
    """指令注册表"""

    def __init__(self):
        self._commands: Dict[str, Type[Command]] = {}

    def register(self, name: str, command_class: Type[Command]):
        """注册指令"""
        self._commands[name] = command_class

    def get_command(self, name: str) -> Optional[Type[Command]]:
        """获取指令类"""
        return self._commands.get(name)

    def get_all_commands(self) -> Dict[str, Type[Command]]:
        """获取所有指令"""
        return self._commands.copy()

    def is_command(self, input_str: str) -> bool:
        """判断输入是否为指令"""
        return input_str.startswith('/') and len(input_str) > 1

    def parse_command(self, input_str: str) -> tuple[str, str]:
        """
        解析指令

        Args:
            input_str: 用户输入

        Returns:
            tuple: (指令名, 参数)
        """
        if not self.is_command(input_str):
            return "", input_str

        parts = input_str[1:].split(' ', 1)
        command_name = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        return command_name, args