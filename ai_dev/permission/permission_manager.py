"""
权限管理器 - 负责工具权限检查和决策
"""

import re
from typing import Dict, List, Optional, Tuple, Any, Set
from enum import Enum
from pathlib import Path

from ai_dev.core.config_manager import ConfigManager
from ai_dev.core.global_state import GlobalState
from ai_dev.utils.file import get_relative_path, get_absolute_path


class PermissionDecision(Enum):
    """权限决策结果"""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"

class UserPermissionChoice(Enum):
    """用户手动授权选择"""
    ALLOW_ONCE = "allow_once"  # 选项1: 仅本次允许
    ALLOW_SESSION = "allow_session"  # 选项2: 本次会话中允许
    DENY = "deny"  # 选项3: 拒绝本次操作

class PermissionRequest:
    """权限请求"""

    def __init__(self, tool_name: str, tool_args: Dict[str, Any], working_directory: str):
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.working_directory = working_directory
        self.permission_key = self._generate_permission_key()

    def _generate_permission_key(self) -> str:
        """生成权限键用于会话缓存"""
        if self.tool_name == "BashExecuteTool":
            command = self.tool_args.get("command", "")
            # 提取命令类型
            command_parts = command.strip().split()
            if command_parts:
                command_type = command_parts[0]
                return f"{self.tool_name}({command_type}:*)"
        elif self.tool_name in ["FileWriteTool", "FileEditTool"]:
            file_path = self.tool_args.get("file_path", "")
            if file_path:
                # 使用相对路径作为键的一部分
                try:
                    rel_path = Path(file_path).relative_to(self.working_directory)
                    return f"{self.tool_name}({str(rel_path)})"
                except ValueError:
                    # 如果路径不在工作目录内，使用绝对路径
                    return f"{self.tool_name}({file_path})"

        return self.tool_name

    def get_display_info(self) -> Dict[str, Any]:
        """获取用于显示的权限请求信息"""
        info = {
            "type": "permission_request",
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "working_directory": self.working_directory,
            "permission_key": self.permission_key
        }

        # 根据工具类型添加特定信息
        if self.tool_name == "FileWriteTool":
            file_path = self.tool_args.get("file_path", "")
            absolute_path = get_absolute_path(file_path)
            relative_path = get_relative_path(absolute_path)
            file_name = absolute_path.name

            # 生成patch信息用于显示
            patch_info = self._get_patch_info(file_path, "", self.tool_args.get("content", ""), is_edit=False)

            info.update({
                "operation_type": "文件写入",
                "absolute_path": str(absolute_path),
                "file_path": str(relative_path),
                "file_name": file_name,
                "content": self.tool_args.get("content", ""),
                "display_type": "file_write"
            })
        elif self.tool_name == "FileEditTool":
            file_path = self.tool_args.get("file_path")
            old_string = self.tool_args.get("old_string", "")
            new_string = self.tool_args.get("new_string", "")

            absolute_path = get_absolute_path(file_path)
            relative_path = get_relative_path(absolute_path)
            file_name = absolute_path.name

            # 生成patch信息用于显示
            patch_info = self._get_patch_info(file_path, old_string, new_string, is_edit=True)

            info.update({
                "operation_type": "文件编辑",
                "absolute_path": str(absolute_path),
                "file_path": str(relative_path),
                "file_name": file_name,
                "old_string": old_string,
                "new_string": new_string,
                "display_type": "file_edit",
                "patch_info": patch_info
            })
        elif self.tool_name == "BashExecuteTool":
            info.update({
                "operation_type": "Bash命令执行",
                "command": self.tool_args.get("command", ""),
                "propose": self.tool_args.get("propose", ""),
                "display_type": "bash_execute"
            })
        else:
            info.update({
                "operation_type": "工具执行",
                "display_type": "generic"
            })

        return info

    def _get_patch_info(self, file_path: str, old_string: str, new_string: str, is_edit: bool) -> Dict[str, Any]:
        """生成patch信息用于显示差异"""
        from pathlib import Path
        from ai_dev.utils.patch import get_patch

        if not file_path:
            return {"hunks": [], "has_changes": False}

        try:
            # 构建安全路径
            if is_edit:
                safe_path = Path(file_path)
                if not safe_path.exists() or not safe_path.is_file():
                    return {"hunks": [], "has_changes": False}

                # 读取文件内容
                with open(safe_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()

                # 如果没有old_string，表示创建新文件
                if not old_string:
                    # 创建新文件的patch
                    hunks = get_patch(file_path, "", "", new_string)
                    return {"hunks": hunks, "has_changes": True}

                # 检查old_string是否在文件中
                if old_string not in file_content:
                    return {"hunks": [], "has_changes": False}

                # 生成patch
                hunks = get_patch(file_path, file_content, old_string, new_string)
                return {"hunks": hunks, "has_changes": len(hunks) > 0}
            else:
                hunks = get_patch(file_path, "", "", new_string)
                return {"hunks": hunks, "has_changes": True}

        except Exception:
            # 如果出现任何错误，返回空patch
            return {"hunks": [], "has_changes": False}


class PermissionManager:
    """权限管理器"""

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        if config_manager is None:
            config_manager = GlobalState.get_config_manager()
        self.config_manager = config_manager
        self.session_cache: Dict[str, PermissionDecision] = {}

    def load_permission_config(self) -> Dict[str, List[str]]:
        """加载权限配置"""
        return self.config_manager.get("permissions", {
            "allow": [
                # "FileListTool",
                "FileReadTool",
                "GlobTool",
                "GrepTool",
                "TodoWriteTool",
                "TaskTool"
            ],
            "deny": [
            ],
            "ask": [
            ]
        })

    def check_permission(self, tool_name: str, tool_args: Dict[str, Any], working_directory: str) -> Tuple[PermissionDecision, PermissionRequest]:
        """检查工具权限

        Returns:
            Tuple[PermissionDecision, PermissionRequest]: (决策结果, 权限请求对象)
        """
        from ..utils.logger import agent_logger

        request = PermissionRequest(tool_name, tool_args, working_directory)

        # 首先检查会话缓存, 只有本次会话允许的才会缓存起来
        if request.permission_key in self.session_cache:
            agent_logger.debug(f"[PERMISSION_DEBUG] 工具 {tool_name} 命中会话缓存，权限键: {request.permission_key}")
            return PermissionDecision.ALLOW, request

        # 检查权限配置
        config = self.load_permission_config()
        agent_logger.debug(f"[PERMISSION_DEBUG] 检查工具 {tool_name} 权限，参数: {tool_args}")

        # 检查拒绝列表（最高优先级）
        if self._matches_any_pattern(request, config.get("deny", [])):
            agent_logger.debug(f"[PERMISSION_DEBUG] 工具 {tool_name} 被拒绝列表匹配，权限键: {request.permission_key}")
            return PermissionDecision.DENY, request

        # 检查允许列表
        if self._matches_any_pattern(request, config.get("allow", [])):
            agent_logger.debug(f"[PERMISSION_DEBUG] 工具 {tool_name} 被允许列表匹配，权限键: {request.permission_key}")
            return PermissionDecision.ALLOW, request

        # 默认行为：询问
        agent_logger.debug(f"[PERMISSION_DEBUG] 工具 {tool_name} 需要用户确认，权限键: {request.permission_key}")
        return PermissionDecision.ASK, request

    def _matches_any_pattern(self, request: PermissionRequest, patterns: List[str]) -> bool:
        """检查请求是否匹配任何权限模式"""
        from ..utils.logger import agent_logger

        for pattern in patterns:
            if self._matches_pattern(request, pattern):
                agent_logger.debug(f"[PERMISSION_DEBUG] 工具 {request.tool_name} 匹配模式: {pattern}")
                return True

        agent_logger.debug(f"[PERMISSION_DEBUG] 工具 {request.tool_name} 未匹配任何模式，检查的模式: {patterns}")
        return False

    def _matches_pattern(self, request: PermissionRequest, pattern: str) -> bool:
        """检查请求是否匹配特定权限模式"""
        # 解析模式：ToolName 或 ToolName(pattern)
        if "(" in pattern and pattern.endswith(")"):
            tool_part, pattern_part = pattern.split("(", 1)
            pattern_part = pattern_part[:-1]  # 移除末尾的")"
        else:
            tool_part = pattern
            pattern_part = None

        # 检查工具名称是否匹配
        if tool_part != request.tool_name:
            return False

        # 如果没有模式部分，匹配所有操作
        if pattern_part is None:
            return True

        # 解析模式部分：command:pattern 或 path_pattern
        if ":" in pattern_part:
            command_type, command_pattern = pattern_part.split(":", 1)
            return self._matches_command_pattern(request, command_type, command_pattern)
        else:
            # 文件路径模式匹配
            return self._matches_path_pattern(request, pattern_part)

    def _matches_command_pattern(self, request: PermissionRequest, command_type: str, command_pattern: str) -> bool:
        """匹配命令模式"""
        if request.tool_name != "BashExecuteTool":
            return False

        command = request.tool_args.get("command", "").strip()

        # 如果没有具体命令，检查是否匹配通用模式
        if not command:
            # 如果模式是"*"，匹配所有命令
            if command_pattern == "*":
                return True
            # 否则不匹配
            return False

        # 提取实际命令类型
        actual_command_parts = command.split()
        if not actual_command_parts:
            return False

        actual_command_type = actual_command_parts[0]

        # 检查命令类型是否匹配
        if command_type != "*" and actual_command_type != command_type:
            return False

        # 检查命令模式
        if command_pattern == "*":
            return True
        else:
            # 使用通配符匹配
            if "*" in command_pattern:
                # 将通配符转换为正则表达式
                regex_pattern = command_pattern.replace("*", ".*")
                try:
                    regex = re.compile(regex_pattern)
                    return bool(regex.search(command))
                except re.error:
                    return False
            else:
                # 精确匹配
                return command_pattern in command

    def _matches_path_pattern(self, request: PermissionRequest, path_pattern: str) -> bool:
        """匹配文件路径模式"""
        if request.tool_name not in ["FileWriteTool", "FileEditTool", "FileReadTool"]:
            return False

        file_path = request.tool_args.get("file_path", "")
        if not file_path:
            return False

        # 如果模式是"*"，匹配所有路径
        if path_pattern == "*":
            return True

        # 使用通配符匹配
        if "*" in path_pattern:
            # 将通配符转换为正则表达式
            regex_pattern = path_pattern.replace("*", ".*")
            try:
                regex = re.compile(regex_pattern)
                return bool(regex.search(file_path))
            except re.error:
                return False
        else:
            # 精确匹配
            return file_path == path_pattern

    def apply_user_choice(self, request: PermissionRequest, choice: UserPermissionChoice) -> bool:
        """应用用户的权限选择

        Args:
            request: 权限请求对象
            choice: 用户选择

        Returns:
            bool: True表示允许执行, False表示拒绝执行
        """
        from ..utils.logger import agent_logger

        if choice == UserPermissionChoice.ALLOW_ONCE:
            # 仅本次允许，不缓存
            agent_logger.debug(f"[PERMISSION_DEBUG] 应用用户选择: 仅本次允许 {request.tool_name}, 权限键: {request.permission_key}")
            return True
        elif choice == UserPermissionChoice.ALLOW_SESSION:
            # 本次会话允许，加入缓存
            self.session_cache[request.permission_key] = PermissionDecision.ALLOW
            agent_logger.debug(f"[PERMISSION_DEBUG] 应用用户选择: 本次会话允许 {request.tool_name}, 权限键: {request.permission_key}")
            return True
        elif choice == UserPermissionChoice.DENY:
            # 拒绝本次操作
            agent_logger.debug(f"[PERMISSION_DEBUG] 应用用户选择: 拒绝 {request.tool_name}, 权限键: {request.permission_key}")
            return False
        else:
            # 未知选择，默认拒绝
            agent_logger.debug(f"[PERMISSION_DEBUG] 应用用户选择: 未知选择 {choice}, 默认拒绝 {request.tool_name}")
            return False

    def clear_session_cache(self):
        """清除会话缓存"""
        self.session_cache.clear()
