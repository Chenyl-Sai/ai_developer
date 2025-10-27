"""
文件列表工具
"""

from pathlib import Path
from typing import Any, Dict, List, Type, Generator, AsyncGenerator
from ai_dev.tools.base import StreamTool, CommonToolArgs
from pydantic import BaseModel, Field
from .prompt_cn import prompt, prompt_too_many_files
from .constant import MAX_FILES

class GlobTool(StreamTool):
    """Glob工具 - 根据模式匹配文件"""

    # LangChain BaseTool要求的属性
    name: str = "GlobTool"
    description: str = prompt

    @property
    def show_name(self) -> str:
        return "Search"

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_parallelizable(self) -> bool:
        return True

    class GlobArgs(CommonToolArgs):
        directory: str = Field(description="The directory to search in. Defaults to the current working directory.")
        pattern: str = Field(description="The glob pattern to match files against")

    args_schema: Type[BaseModel] = GlobArgs

    async def _execute_tool(self, directory: str, pattern: str, **kwargs) -> AsyncGenerator[dict, None]:
        """执行文件模式匹配"""
        import json

        safe_dir = self._safe_join_path(directory)

        if not safe_dir.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        if not safe_dir.is_dir():
            raise ValueError(f"Path is not a directory: {directory}")

        files = []
        for path in safe_dir.glob(pattern):
            if path.is_file():
                files.append({
                    "name": path.name,
                    "path": str(path),
                    "size": path.stat().st_size,
                    "modified": path.stat().st_mtime
                })

        if files:
            files.sort(key=lambda f: f["modified"])

        found_file_count = len(files)
        result_data = ""
        if found_file_count > MAX_FILES:
            files = files[:MAX_FILES]
            result_data = prompt_too_many_files

        result_data += json.dumps(files, ensure_ascii=False, indent=2)

        yield {
            "type": "tool_end",
            "source": kwargs.get("context").get("agent_id"),
            "result_for_llm": result_data,
            "context": kwargs.get("context"),
            "result_for_show": {
                "found_file_count": len(files),
            }
        }

    def _get_success_message(self, result_for_show: Any) -> str:
        return f"Found <b>{result_for_show.get('found_file_count')}</b> files"