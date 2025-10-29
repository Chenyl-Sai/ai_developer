"""
文件搜索工具
"""

from pathlib import Path
from typing import Any, Dict, List, Type, Generator, AsyncGenerator

from langchain_core.callbacks import Callbacks
from langchain_core.tools import BaseTool

from ai_dev.utils.tool import CommonToolArgs
from pydantic import BaseModel, Field
from ai_dev.core.global_state import GlobalState
from .constant import MAX_FILES
from .prompt_cn import prompt, prompt_too_many_files
from ...utils.file import get_absolute_path
from ...utils.tool import tool_start_callback_handler, tool_end_callback_handler, tool_error_callback_handler


class GrepTool(BaseTool):
    """文件搜索工具"""

    # LangChain BaseTool要求的属性
    name: str = "GrepTool"
    description: str = prompt
    response_format: str = "content_and_artifact"

    callbacks: Callbacks = [tool_start_callback_handler, tool_end_callback_handler, tool_error_callback_handler]

    @property
    def is_parallelizable(self) -> bool:
        return True

    class GrepArgs(CommonToolArgs):
        pattern: str = Field(description="The regular expression pattern to search for in file contents")
        directory: str = Field(default="", description="The directory to search in. Defaults to the current working directory.")
        file_pattern: str = Field(default="", description="File pattern to include in the search (e.g. '*.js', '*.{ts,tsx}')")

    args_schema: Type[BaseModel] = GrepArgs

    def _run(self, pattern: str, directory: str = "", file_pattern: str = "", **kwargs) -> Any:
        """执行文件搜索"""
        import subprocess
        import os
        import json

        # 如果 directory 为空，使用当前工作目录
        if not directory:
            search_dir = GlobalState.get_working_directory()
        else:
            safe_dir = get_absolute_path(directory)
            if not safe_dir.exists():
                raise FileNotFoundError(f"Directory not found: {directory}")
            if not safe_dir.is_dir():
                raise ValueError(f"Path is not a directory: {directory}")
            search_dir = safe_dir

        # 构建 ripgrep 命令
        cmd = ["rg", "-li", "--sort", "modified"]

        # 如果指定了文件模式，添加文件类型过滤
        if file_pattern:
            cmd.extend(["--glob", file_pattern])

        cmd.extend([pattern, str(search_dir)])

        try:
            # 执行 ripgrep 命令
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=search_dir)

            if result.returncode == 0:
                # 成功找到匹配的文件
                files = result.stdout.strip().split('\n')
                files = [f for f in files if f]  # 移除空行

                # 转换为相对路径并添加文件信息
                results = []
                for file_path in files:
                    full_path = Path(search_dir) / file_path
                    if full_path.exists():
                        results.append({
                            "name": full_path.name,
                            "path": str(full_path),
                            "modified": full_path.stat().st_mtime
                        })

                result_data = ""
                if len(results) > MAX_FILES:
                    results = results[:MAX_FILES]
                    result_data = prompt_too_many_files
                result_data += json.dumps(results, ensure_ascii=False, indent=2)

                return result_data, {
                    "found_file_count": len(results),
                }

            elif result.returncode == 1:
                # 没有找到匹配的文件
                result_data = "[]"
                return result_data, {
                    "found_file_count": 0,
                }

            else:
                # ripgrep 执行出错
                raise RuntimeError(f"ripgrep command failed: {result.stderr}")

        except FileNotFoundError:
            raise RuntimeError("ripgrep command not found. Please install ripgrep (rg) to use this tool.")