
from ai_dev.tools import *

file_read_tool = FileReadTool()
file_edit_tool = FileEditTool()
file_write_tool = FileWriteTool()
file_list_tool = FileListTool()
grep_tool = GrepTool()
task_tool = TaskTool()
todo_write_tool = TodoWriteTool()
bash_execute_tool = BashExecuteTool()

def get_all_tools() -> list[MyBaseTool]:
    return [file_read_tool, file_edit_tool, file_write_tool, file_list_tool,
            grep_tool, task_tool, todo_write_tool, bash_execute_tool]

def get_available_tools() -> list[MyBaseTool]:
    return [tool for tool in get_all_tools() if tool.is_available]

def get_tool_by_name(name: str) -> MyBaseTool:
    return next(filter(lambda tool: tool.name == name and tool.is_available, get_all_tools()), None)

def get_tools_by_names(names: list[str]) -> list[MyBaseTool]:
    return [tool for tool in get_available_tools() if tool.is_available and tool.name in names]

def get_readonly_tools() -> list[MyBaseTool]:
    return [tool for tool in get_all_tools() if tool.is_available and tool.is_readonly]