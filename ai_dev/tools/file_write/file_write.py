"""
文件写入工具
"""

from pathlib import Path
from typing import Any, Dict, Type, Generator, AsyncGenerator

from langchain_core.callbacks import Callbacks
from langchain_core.tools import BaseTool

from ai_dev.utils.tool import CommonToolArgs
from pydantic import BaseModel, Field
from ai_dev.utils.file import detect_file_encoding, detect_line_endings_direct, write_text_content, get_absolute_path
from ai_dev.utils.patch import get_patch
from ai_dev.core.global_state import GlobalState
from ai_dev.utils.freshness import update_agent_edit_time, check_freshness
from .prompt_cn import prompt
from ...utils.tool import tool_start_callback_handler, tool_end_callback_handler, tool_error_callback_handler


class FileWriteTool(BaseTool):
    """文件写入工具"""

    # LangChain BaseTool要求的属性
    name: str = "FileWriteTool"
    description: str = prompt
    response_format: str = "content_and_artifact"

    callbacks: Callbacks = [tool_start_callback_handler, tool_end_callback_handler, tool_error_callback_handler]

    class FileWriteArgs(CommonToolArgs):
        file_path: str = Field(description="The absolute path to the file to write (must be absolute, not relative)")
        content: str = Field(description="The content to write to the file")

    args_schema: Type[BaseModel] = FileWriteArgs

    def _run(self, file_path: str, content: str, **kwargs) -> Any:
        """执行文件写入"""
        import json

        safe_path = get_absolute_path(file_path)
        old_file_exists = safe_path.exists()
        
        # 如果文件已存在，检查是否被读取过
        if old_file_exists:
            need_refresh, reason = check_freshness(str(safe_path))
            if need_refresh:
                raise ValueError(f"修改失败: {reason}")
        
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
        
        # 更新agent修改时间
        if old_file_exists:
            update_agent_edit_time(str(safe_path))

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

        return result_data, {}