"""
/clear 指令 - 清除对话历史
"""

from ..commands import Command
from rich.console import Console

console = Console()


class ClearCommand(Command):
    """清除对话历史指令"""

    def execute(self, cli, args: str) -> bool:
        """执行清除指令"""
        cli.assistant.reset_conversation()
        console.print("[green]对话历史已清除[/green]")
        return True

    @property
    def description(self) -> str:
        return "清除对话历史"