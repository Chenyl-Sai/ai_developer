
from ai_dev.tools import *

file_read_tool = FileReadTool()
file_edit_tool = FileEditTool()
file_write_tool = FileWriteTool()
file_list_tool = FileListTool()
grep_tool = GrepTool()
task_tool = TaskTool()
todo_write_tool = TodoWriteTool()
bash_execute_tool = BashExecuteTool()

async def get_all_tools() -> list[BaseTool]:
    return [file_read_tool, file_edit_tool, file_write_tool, file_list_tool,
            grep_tool, task_tool, todo_write_tool, bash_execute_tool]

async def get_available_tools() -> list[BaseTool]:
    return [tool for tool in await get_all_tools() if tool.is_available]

async def get_tool_by_name(name: str) -> BaseTool:
    return next(filter(lambda tool: tool.name == name and tool.is_available, await get_all_tools()), None)

async def get_tools_by_names(names: list[str]) -> list[BaseTool]:
    return [tool for tool in await get_available_tools() if tool.is_available and tool.name in names]

async def get_readonly_tools() -> list[BaseTool]:
    return [tool for tool in await get_all_tools() if tool.is_available and tool.is_readonly]