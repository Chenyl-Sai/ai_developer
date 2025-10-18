"""
文件写入工具
"""

from pathlib import Path
from typing import Any, Dict, Type, Generator
from .base import StreamTool, CommonToolArgs
from pydantic import BaseModel, Field
from ai_dev.utils.file import detect_file_encoding, detect_line_endings_direct, write_text_content
from ai_dev.utils.patch import get_patch
from ai_dev.core.global_state import GlobalState

DESCRIPTION = """Write a file to the local filesystem. Overwrites the existing file if there is one.

Before using this tool:

1. Use the ReadFile tool to understand the file's contents and context

2. Directory Verification (only applicable when creating new files):
   - Use the LS tool to verify the parent directory exists and is the correct location"""

class FileWriteTool(StreamTool):
    """文件写入工具"""

    # LangChain BaseTool要求的属性
    name: str = "FileWriteTool"
    description: str = DESCRIPTION

    @property
    def show_name(self) -> str:
        return "Write"

    @property
    def is_readonly(self) -> bool:
        return False

    @property
    def is_parallelizable(self) -> bool:
        return False

    class FileWriteArgs(CommonToolArgs):
        file_path: str = Field(description="The absolute path to the file to write (must be absolute, not relative)")
        content: str = Field(description="The content to write to the file")

    args_schema: Type[BaseModel] = FileWriteArgs

    def _execute_tool(self, file_path: str, content: str, **kwargs) -> Generator[Dict[str, Any], None, None]:
        """执行文件写入"""
        import json

        safe_path = self._safe_join_path(file_path)
        old_file_exists = safe_path.exists()
        enc = detect_file_encoding(str(safe_path)) if old_file_exists else "utf-8"
        endings = detect_line_endings_direct(str(safe_path), encoding=enc) if old_file_exists else "LR"

        old_content = None
        if old_file_exists:
            with open(safe_path, "r", encoding=enc, errors="ignore") as f:
                old_content = f.read()

        # 确保目录存在
        safe_path.parent.mkdir(parents=True, exist_ok=True)

        # 写文件
        write_text_content(str(safe_path), content, enc, endings)

        patch = get_patch(
            file_path=file_path,
            file_contents=old_content if old_content else "",
            old_str=old_content if old_content else "",
            new_str=content
        )

        # 生成返回数据
        result_data = {
            "type": "update" if old_content else "create",
            "file_path": str(safe_path.relative_to(GlobalState.get_working_directory())),
            "absolute_path": str(safe_path),
            "file_name": safe_path.name,
            "content": content,
            "patch": patch,
        }

        yield {
            "type": "tool_end",
            "result_for_llm": result_data,
        }

    def _format_args(self, kwargs: Dict[str, Any]) -> str:
        safe_path = self._safe_join_path(kwargs.get("file_path"))
        relative_path = str(safe_path.relative_to(GlobalState.get_working_directory()))
        return f"{relative_path}"

    def _get_success_message(self, llm_result) -> str:
        hunks = llm_result.get("patch")
        total_add = 0
        for hunk in hunks if hunks else []:
            total_add += len(hunk["lines"])

        return f"Wrote <bold>{total_add}</bold> lines to <bold>{llm_result.get('file_path')}</bold>"