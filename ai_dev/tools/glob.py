"""
文件列表工具
"""

from pathlib import Path
from typing import Any, Dict, List, Type, Generator
from .base import StreamTool
from pydantic import BaseModel, Field

DESCRIPTION = """- Fast file pattern matching tool that works with any codebase size
- Supports glob patterns like "**/*.js" or "src/**/*.ts"
- Returns matching file paths sorted by modification time
- Use this tool when you need to find files by name patterns
- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead"""

class GlobTool(StreamTool):
    """Glob工具 - 根据模式匹配文件"""

    # LangChain BaseTool要求的属性
    name: str = "GlobTool"
    description: str = DESCRIPTION
    found_file_count: int = 0

    @property
    def show_name(self) -> str:
        return "Search"

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_parallelizable(self) -> bool:
        return True

    class GlobArgs(BaseModel):
        directory: str = Field(description="The directory to search in. Defaults to the current working directory.")
        pattern: str = Field(description="The glob pattern to match files against")

    args_schema: Type[BaseModel] = GlobArgs

    def _execute_tool(self, directory: str, pattern: str) -> Generator[Dict[str, Any], None, None]:
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

        self.found_file_count = len(files)

        result_data = json.dumps(files, ensure_ascii=False, indent=2)

        yield {
            "type": "result",
            "result_for_llm": result_data,
            "show_message": f"搜索完成，找到 {self.found_file_count} 个文件"
        }

    def _get_success_message(self, result: str) -> str:
        return f"  ⎿ Found <b>{self.found_file_count}</b> files"