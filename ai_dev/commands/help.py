"""
/help 指令 - 显示帮助信息
"""

from ..commands import Command, CommandRegistry
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


class HelpCommand(Command):
    """帮助指令"""

    def execute(self, cli, args: str) -> bool:
        """执行帮助指令"""
        # 获取所有注册的指令
        command_registry = cli.command_registry
        commands = command_registry.get_all_commands()

        # 创建指令表格
        table = Table(title="可用指令")
        table.add_column("指令", style="cyan")
        table.add_column("描述", style="green")

        for cmd_name, cmd_class in commands.items():
            cmd_instance = cmd_class()
            table.add_row(f"/{cmd_name}", cmd_instance.description)

        console.print(table)

        # 显示自然语言处理说明
        natural_language_help = """
自然语言处理：
您可以直接输入自然语言问题，AI助手会帮您：
• 读取和编辑文件
• 搜索代码内容
• 执行系统命令
• 管理项目环境
• 回答编程相关问题
        """

        panel = Panel(
            natural_language_help,
            title="自然语言交互",
            border_style="blue"
        )
        console.print(panel)

        return True

    @property
    def description(self) -> str:
        return "显示帮助信息"