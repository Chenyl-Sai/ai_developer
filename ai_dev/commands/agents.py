"""
/agents 指令 - 显示可用代理列表
"""

from ..commands import Command
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


class AgentsCommand(Command):
    """显示代理列表指令"""

    def execute(self, cli, args: str) -> bool:
        """执行代理列表指令"""
        # 创建表格
        table = Table(title="可用代理")
        table.add_column("名称", style="cyan")
        table.add_column("描述", style="green")
        table.add_column("状态", style="yellow")

        # 添加示例代理（实际项目中可以从配置或注册表中获取）
        table.add_row("AI编程助手", "帮助进行代码开发和文件操作", "活跃")
        table.add_row("代码审查", "分析代码质量和潜在问题", "待实现")
        table.add_row("文档生成", "自动生成代码文档", "待实现")
        table.add_row("测试生成", "生成单元测试用例", "待实现")

        console.print(table)
        return True

    @property
    def description(self) -> str:
        return "显示可用代理列表"