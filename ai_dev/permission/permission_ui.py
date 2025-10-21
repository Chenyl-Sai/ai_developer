"""
权限交互界面适配器 - 适配AdvancedCLI
"""

from typing import Dict, Any

from prompt_toolkit.formatted_text import FormattedText

from ai_dev.constants.product import PRODUCT_NAME
from ai_dev.core.global_state import GlobalState
from ai_dev.utils.logger import agent_logger
from ai_dev.utils.render import render_hunks


class PermissionUI:
    """权限交互界面适配器 - 用于AdvancedCLI"""

    def __init__(self, cli_instance):
        self.cli = cli_instance

    def display_permission_request(self, request_info: Dict[str, Any]) -> str:
        """显示权限请求界面并获取用户选择"""
        # 格式化权限请求内容
        formatted_text, options = self._format_permission_choice(request_info)
        # 使用AdvancedCLI的动态输入域切换显示权限请求
        self.cli.show_permission_request(formatted_text, options)

        # 返回空字符串，实际选择由AdvancedCLI处理
        return ""

    def _format_permission_choice(self, request_info: dict) -> tuple[FormattedText, list]:
        """格式化权限选择界面 - 适配多种权限类型"""
        display_type = request_info.get("display_type", "generic")

        if display_type == "file_write":
            return self._format_file_write_request(request_info)
        elif display_type == "file_edit":
            return self._format_file_edit_request(request_info)
        elif display_type == "bash_execute":
            return self._format_bash_execute_request(request_info)
        else:
            return self._format_generic_request(request_info)

    def _format_file_write_request(self, request_info: dict) -> tuple[FormattedText, list]:
        """格式化文件写入权限请求"""
        file_path = request_info.get("file_path", "")
        file_name = request_info.get("file_name", "")
        patch_info = request_info.get("patch_info", {})

        hunks = patch_info.get("hunks", [])
        result = []
        result.append(("class:permission.title", f" Create File({file_path})\n\n"))
        result.extend(render_hunks(hunks))
        result.append(("", " \n \n"))
        result.append(("", f" Do you want to create {file_name}?\n"))
        options = [
            "1. Yes",
            "2. Yes, allow all edits during this session",
            f"3. No, and tell {PRODUCT_NAME} what to do differently",
        ]

        return FormattedText(result), options

    def _format_file_edit_request(self, request_info: dict) -> tuple[FormattedText, list]:
        """格式化文件编辑权限请求"""
        file_path = request_info.get("file_path", "")
        file_name = request_info.get("file_name", "")
        patch_info = request_info.get("patch_info", {})

        hunks = patch_info.get("hunks", [])
        result = []
        result.append(("class:permission.title", f" Edit File({file_path})\n\n"))
        result.extend(render_hunks(hunks))
        result.append(("", " \n \n"))
        result.append(("", f" Do you want to make this edit to {file_name}?\n"))

        options = [
            "1. Yes",
            "2. Yes, allow all edits during this session",
            f"3. No, and tell {PRODUCT_NAME} what to do differently",
        ]

        return FormattedText(result), options

    def _format_bash_execute_request(self, request_info: dict) -> tuple[FormattedText, list]:
        """格式化Bash命令执行权限请求"""
        command = request_info.get("command", "")
        propose = request_info.get("propose", "")

        command_type = command
        command_parts = command.strip().split()
        if command_parts:
            command_type = command_parts[0]

        result = []
        result.append(("class:permission.title", f" Bash command\n\n"))
        result.append(("", f"   {command}\n"))
        result.append(("class:common.gray", f"   {propose}"))
        result.append(("", " \n \n"))
        result.append(("", f" Do you want to proceed\n"))
        options = [
            "1. Yes",
            f"2. Yes, and don't ask again for {command_type} commands in {GlobalState.get_working_directory()}",
            f"3. No, and tell {PRODUCT_NAME} what to do differently",
        ]
        return FormattedText(result), options

    def _format_generic_request(self, request_info: dict) -> tuple[FormattedText, list]:
        """格式化通用权限请求"""
        tool_name = request_info.get('tool_name')
        tool_args = request_info.get("tool_args", {})
        text = ""
        if tool_args:
            for key, value in tool_args.items():
                text += f" {key} : {value}\n"

        result = []
        result.append(("class:permission.title", f" Execute tool\n\n"))
        result.append(("", f"   Tool name: {tool_name}\n"))
        result.append(("", f"   Tool args: {text}"))
        result.append(("", " \n \n"))
        result.append(("", f" Do you want to proceed\n"))
        options = [
            "1. Yes",
            f"2. Yes, and don't ask again for {tool_name} tool during this session",
            f"3. No, and tell {PRODUCT_NAME} what to do differently",
        ]
        return FormattedText(result), options