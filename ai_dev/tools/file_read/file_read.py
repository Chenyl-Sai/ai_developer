"""
文件读取工具
"""

from typing import Any, Dict, Type

from langchain_core.tools import BaseTool

from ai_dev.utils.tool import CommonToolArgs
from pydantic import BaseModel, Field
from langchain_core.callbacks import Callbacks

from ai_dev.core.global_state import GlobalState
from ai_dev.utils.freshness import update_read_time
from .prompt_cn import prompt
from .constant import MAX_LINE_LENGTH, MAX_LINES_TO_READ
from ...utils.file import get_absolute_path
from ...utils.tool import tool_start_callback_handler, tool_error_callback_handler, tool_end_callback_handler


class FileReadTool(BaseTool):
    """文件读取工具"""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    # LangChain BaseTool要求的属性
    name: str = "FileReadTool"
    description: str = prompt
    response_format: str = "content_and_artifact"

    class FileReadArgs(CommonToolArgs):
        file_path: str = Field(description="The absolute path to the file to read")
        offset: int = Field(default=1, description="The line number to start reading from. Only provide if the file is too large to read at once")
        limit: int = Field(default=None, description="The number of lines to read. Only provide if the file is too large to read at once.")

    args_schema: Type[BaseModel] = FileReadArgs

    callbacks: Callbacks = [tool_start_callback_handler, tool_end_callback_handler, tool_error_callback_handler]

    @property
    def is_parallelizable(self) -> bool:
        return True

    def _run(self, file_path: str, offset: int = 1, limit: int = None, **kwargs) -> Any:
        """执行文件读取"""
        safe_path = get_absolute_path(file_path)

        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not safe_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # 读取文件所有内容
        with safe_path.open(encoding="utf-8") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)

        # 处理offset参数（从1开始计数）
        start_line = max(0, offset - 1)  # 转换为0-based索引

        # 处理limit参数
        if limit is None:
            limit = min(MAX_LINES_TO_READ, total_lines - start_line)
        else:
            limit = min(limit, total_lines - start_line)

        # 截取指定行范围
        selected_lines = all_lines[start_line:start_line + limit]

        # 处理行长度限制
        processed_lines = []
        for line in selected_lines:
            if len(line) > MAX_LINE_LENGTH:
                processed_lines.append(line[:MAX_LINE_LENGTH] + "...")
            else:
                processed_lines.append(line)

        content = "".join(processed_lines)

        # 更新文件读取时间
        update_read_time(str(safe_path))

        result_data = {
            "file_path": str(safe_path.relative_to(GlobalState.get_working_directory())),
            "absolute_path": str(safe_path),
            "file_name": safe_path.name,
            "content": content,
            "start_line": offset,
            "line_count": len(selected_lines),
            "total_lines": total_lines
        }
        return result_data, {}