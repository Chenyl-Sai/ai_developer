"""
文件编辑工具
"""

from typing import Any, Dict, Type, Literal, Generator, AsyncGenerator

from langchain_core.tools import BaseTool
from langchain_core.callbacks import Callbacks

from ai_dev.utils.tool import CommonToolArgs
from pydantic import BaseModel, Field
from ai_dev.utils.file import detect_file_encoding, detect_line_endings_direct, write_text_content, get_absolute_path
from ai_dev.utils.patch import get_patch
from ai_dev.core.global_state import GlobalState
from ai_dev.utils.freshness import check_freshness, update_agent_edit_time
from .prompt_cn import prompt
from ...utils.tool import tool_start_callback_handler, tool_end_callback_handler, tool_error_callback_handler


class FileEditTool(BaseTool):
    """文件编辑工具"""

    # LangChain BaseTool要求的属性
    name: str = "FileEditTool"
    description: str = prompt
    response_format: str = "content_and_artifact"

    callbacks: Callbacks = [tool_start_callback_handler, tool_end_callback_handler, tool_error_callback_handler]

    class FileEditArgs(CommonToolArgs):
        file_path: str = Field(description="The absolute path to the file to modify")
        old_string: str = Field(description="The text to replace")
        new_string: str = Field(description="The text to replace it with")

    args_schema: Type[BaseModel] = FileEditArgs

    def _run(self, file_path: str, old_string: str, new_string: str = None, **kwargs) -> Any:
        """执行文件编辑"""
        safe_path = get_absolute_path(file_path)
        old_file_exists = safe_path.exists()
        enc = detect_file_encoding(str(safe_path)) if old_file_exists else "utf-8"
        endings = detect_line_endings_direct(str(safe_path), encoding=enc) if old_file_exists else "LR"

        # 参数校验
        self._verify_input(file_path, old_string, new_string)

        # 新鲜度检查 - 在修改前检查文件是否已被外部修改
        if old_file_exists:
            need_refresh, reason = check_freshness(str(safe_path))
            if need_refresh:
                raise ValueError(f"修改失败: {reason}")

        # 生成patch及修改文件全部内容
        patch, original_file, update_file = self._apply_edit(file_path, old_string, new_string)

        # 写文件
        write_text_content(str(safe_path), update_file, enc, endings)
        
        # 更新agent修改时间
        update_agent_edit_time(str(safe_path))

        result_data = {
            "file_path": str(safe_path.relative_to(GlobalState.get_working_directory())),
            "absolute_path": str(safe_path),
            "file_name": safe_path.name,
            "old_string": old_string,
            "new_string": new_string,
            "origin_file": original_file,
            "patch": patch,
        }
        return result_data, {}


    def _verify_input(self, file_path: str, old_string: str, new_string: str):
        """
        校验模型入参是否符合要求
        """
        safe_path = get_absolute_path(file_path)

        # 允许文件不存在时创建新的文件，如果存在的时候做一些校验
        if safe_path.exists():
            if not safe_path.is_file():
                raise ValueError(f"Path is not a file: {file_path}")

            # 校验old_string与new_string是否相同
            if old_string == new_string:
                raise ValueError("No changes to make: old_string and new_string are exactly the same.")

            # 文件存在时old_string不能为空(old_string为空代表创建新文件)
            if not old_string:
                raise ValueError("Cannot create new file - file already exists.")

            # 校验文件是否包含old_string(精确匹配的，包含空格、换行)
            with safe_path.open("r", encoding=detect_file_encoding(str(safe_path))) as f:
                original_file = f.read()
            if old_string not in original_file:
                raise ValueError("String to replace not found in file.")

            # old_string是否匹配到了多个符合条件的地方
            matches = original_file.count(old_string)
            if matches > 1:
                raise ValueError(f"Found {matches} matches of the string to replace. For safety, this tool only supports replacing exactly one occurrence at a time. Add more lines of context to your edit and try again.")


    def _apply_edit(self, file_path: str, old_string: str, new_string: str):
        """
        对文件进行修改操作前的处理
        """
        safe_path = get_absolute_path(file_path)
        original_file = ""
        updated_file = ""
        if not old_string:
            original_file = ""
            updated_file = new_string
        else:
            encoding = detect_file_encoding(str(safe_path))
            with safe_path.open(encoding=encoding) as f:
                original_file = f.read()
            if new_string:
                updated_file = original_file.replace(old_string, new_string)
            else:
                if not old_string.endswith("\n") and (old_string + "\n") in original_file:
                    updated_file = original_file.replace(old_string + "\n", new_string)
                else:
                    updated_file = original_file.replace(old_string, new_string)

        if original_file == updated_file:
            raise ValueError("Original and edited file match exactly. Failed to apply edit.")

        patch = get_patch(file_path, original_file, original_file, updated_file)

        return patch, original_file, updated_file