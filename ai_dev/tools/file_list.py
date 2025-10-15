"""
文件列表工具
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Generator
from .base import StreamTool
import os
from pydantic import BaseModel, Field

DESCRIPTION="Lists files and directories in a given path. The path parameter must be an absolute path, not a relative path. You should generally prefer the Glob and Grep tools, if you know which directories to search."
MAX_FILES = 1000

class FileListTool(StreamTool):
    """LS工具 - 深度优先遍历目录下的所有文件和文件夹，返回树形结构"""

    # LangChain BaseTool要求的属性
    name: str = "FileListTool"
    description: str = DESCRIPTION
    found_file_count: int = 0

    class FileListArgs(BaseModel):
        path: str = Field(description="The absolute path to the directory to list (must be absolute, not relative)")

    args_schema: Type[BaseModel] = FileListArgs

    @property
    def show_name(self) -> str:
        return "LS"

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_parallelizable(self) -> bool:
        return True

    def _skip(self, path: str) -> bool:
        base = os.path.basename(path)

        rules = [
            # 忽略以 "." 开头的文件/目录（但不包括当前目录 ".")
            (path != "." and base.startswith(".")),

            # 忽略 __pycache__ 目录本身
            (os.path.isdir(path) and base == "__pycache__"),

            # 忽略 __pycache__ 下的文件
            (f"{os.sep}__pycache__{os.sep}" in path),
        ]

        return any(rules)

    def _depth_first_traverse(self, directory: Path, file_count: List[int], max_files: int = MAX_FILES) -> List[Dict[str, Any]]:
        """深度优先遍历目录"""
        items = []

        try:
            for path in directory.iterdir():
                if file_count[0] >= max_files:
                    return items

                if self._skip(str(path)):
                    continue

                item = {
                    "name": path.name,
                    "path": str(path),
                    "type": "file" if path.is_file() else "directory"
                }

                file_count[0] += 1

                if path.is_dir():
                    # 递归遍历子目录
                    children = self._depth_first_traverse(path, file_count, max_files)
                    item["children"] = children

                items.append(item)
        except (PermissionError, OSError):
            # 忽略权限错误等
            pass

        return items

    def _build_tree_structure(self, items: List[Dict[str, Any]], root_path: Path) -> Dict[str, Any]:
        """构建树形结构"""
        return {
            "name": str(root_path),
            "path": str(root_path),
            "type": "directory",
            "children": items
        }

    def _format_tree_to_string(self, tree: Dict[str, Any], level: int = 0, is_last: bool = True) -> str:
        """将树形结构格式化为缩进良好的字符串"""
        indent = "  " * level
        prefix = "- "

        result = f"{indent}{prefix}{tree['name']}"

        if "children" in tree and tree["children"]:
            for i, child in enumerate(tree["children"]):
                is_last_child = i == len(tree["children"]) - 1
                result += "\n" + self._format_tree_to_string(child, level + 1, is_last_child)

        return result

    def _execute_tool(self, path: str) -> Generator[Dict[str, Any], None, None]:
        """执行目录遍历"""
        safe_dir = self._safe_join_path(path)

        if not safe_dir.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        if not safe_dir.is_dir():
            raise ValueError(f"Path is not a directory: {path}")

        # 深度优先遍历
        file_count = [0]  # 使用列表来传递引用
        items = self._depth_first_traverse(safe_dir, file_count, MAX_FILES)

        # 构建树形结构
        tree = self._build_tree_structure(items, safe_dir)

        # 格式化为字符串
        formatted_tree = self._format_tree_to_string(tree)

        # 添加统计信息
        if file_count[0] < MAX_FILES:
            result_data = formatted_tree
            self.found_file_count = file_count[0]
        else:
            result_data = f"There are more than {MAX_FILES} files in the repository. Use the LS tool (passing a specific path), BashExecuteTool tool, and other tools to explore nested directories. The first {MAX_FILES} files and directories are included below:\n\n"
            result_data += formatted_tree
            self.found_file_count = MAX_FILES

        yield {
            "type": "result",
            "result_for_llm": result_data,
            "show_message": f"目录遍历完成，找到 {self.found_file_count} 个文件/目录"
        }

    def _format_args(self, kwargs: Dict[str, Any]) -> str:
        return kwargs.get("path")

    def _get_success_message(self, result: str) -> str:
        return f"  ⎿ Found <b>{self.found_file_count}</b> files"