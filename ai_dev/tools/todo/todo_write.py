"""
TodoWrite工具 - 用于创建和管理任务列表
"""
import asyncio
import json
from typing import Any, Dict, List, Optional, Type, Literal, Generator, AsyncGenerator
from uuid import uuid4

from ai_dev.tools import StreamTool
from pydantic import BaseModel, Field
from ai_dev.constants.product import MAIN_AGENT_ID
from ai_dev.tools.base import CommonToolArgs
from .prompt_cn import prompt


class TodoItem(BaseModel):
    """待办事项模型"""
    id: str = Field(default_factory=lambda: str(uuid4()), description="任务唯一标识")
    content: str = Field(description="任务内容描述")
    status: Literal["pending", "in_progress", "completed"] = Field(default="pending", description="任务状态: pending, in_progress, completed")
    priority: str = Field(default="medium", description="任务优先级: low, medium, high")


class TodoWriteArgs(CommonToolArgs):
    """TodoWrite工具参数模型"""
    todos: List[TodoItem] = Field(description="待办事项列表，每个对象包含content、status、priority、id字段")


class TodoWriteTool(StreamTool):
    """TodoWrite工具 - 用于创建和管理任务列表"""

    name: str = "TodoWriteTool"
    description: str = prompt

    @property
    def show_name(self) -> str:
        return "Todo"

    @property
    def is_readonly(self) -> bool:
        return False

    @property
    def is_parallelizable(self) -> bool:
        return False

    args_schema: Type[BaseModel] = TodoWriteArgs

    async def _execute_tool(self, todos: List[TodoItem], **kwargs) -> AsyncGenerator[dict, None]:
        """
        执行TodoWrite工具

        Args:
            todos: 待办事项列表，每个对象包含content、status、priority、id字段

        Returns:
            操作结果描述
        """

        # 验证输入数据
        self._verify_input(todos)

        # 保存待办 - 从kwargs中获取agent_id，如果不存在则使用默认值
        context = kwargs.get("context")
        agent_id = context.get("agent_id", MAIN_AGENT_ID)

        from ai_dev.utils.todo import set_todos, delete_todo_file_if_need
        stored_todo_items = await set_todos(todos, agent_id)

        result_data = self._generate_summary(stored_todo_items)

        # 生成响应之后，查看是否需要清理待办文件
        asyncio.create_task(delete_todo_file_if_need(agent_id))

        yield {
            "type": "tool_end",
            "source": agent_id,
            "result_for_llm": result_data,
            "context": context
        }

    def _verify_input(self, todos: list[TodoItem]):
        """
        校验参数是否合法
        """
        # id是否唯一
        uniq_ids = set([todo.id for todo in todos])
        if len(uniq_ids) != len(todos):
            raise ValueError("Duplicate todo IDs found")
        # 是否只有一个 in_progress 状态的任务
        in_progress_count = len([todo for todo in todos if todo.status == "in_progress"])
        if in_progress_count > 1:
            raise ValueError("Only one task can be in_progress at a time")

        for todo in todos:
            # 任务是否有content
            if not todo.content:
                raise ValueError(f"Todo with ID {todo.id} has empty content")

            # 任务状态是否合法
            if todo.status not in ["pending", "in_progress", "completed"]:
                raise ValueError(f"Invalid status {todo.status} for todo {todo.id}")

            # 任务优先级是否合法
            if todo.priority not in ["low", "medium", "high"]:
                raise ValueError(f"Invalid priority {todo.priority} for todo {todo.id}")

    def _generate_summary(self, todos: List[TodoItem]) -> str:
        """
        生成待办事项摘要

        Args:
            todos: 验证后的待办事项列表

        Returns:
            摘要字符串
        """
        # 统计任务状态
        pending_count = sum(1 for todo in todos if todo.status == "pending")
        in_progress_count = sum(1 for todo in todos if todo.status == "in_progress")
        completed_count = sum(1 for todo in todos if todo.status == "completed")

        # 返回格式化结果
        summary = f"Updated {len(todos)} todo(s), "

        # 如果有进行中的任务，显示详细信息
        if in_progress_count > 0:
            summary += f"({pending_count} pending, {in_progress_count} in progress, {completed_count} completed)"
        summary += '. Continue tracking your progress with the todo list.'

        return summary

    def _send_tool_start_event(self):
        return False

    def _get_success_message(self, result_for_show: Any) -> str:
        """生成成功消息"""
        return ""