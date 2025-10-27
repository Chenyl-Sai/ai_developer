"""
TaskTool - 用于创建子智能体的工具
"""

import asyncio, uuid
from typing import Any, Type

from langchain_core.messages import AIMessage, BaseMessage

from ai_dev.tools.base import CommonToolArgs, MyBaseTool
from ai_dev.constants.product import MAIN_AGENT_ID
from ai_dev.constants.prompt_cn import get_sub_agent_prompt
from ai_dev.core.event_manager import event_manager, EventType
from ai_dev.utils.logger import agent_logger
from ai_dev.utils.subagent import get_sub_agent_by_name, get_agent_descriptions
from pydantic import BaseModel, Field
from langgraph.config import get_stream_writer
from .prompt_cn import prompt

class TaskTool(MyBaseTool):
    """任务工具 - 用于创建子智能体处理复杂任务"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 注册中断事件监听
        # 订阅用户中断请求
        self._user_canceled = False
        event_manager.subscribe(EventType.USER_CANCEL, self._process_user_cancel)

    def _process_user_cancel(self, event):
        self._user_canceled = True

    # LangChain BaseTool要求的属性
    name: str = "TaskTool"
    description: str = prompt
    @property
    def show_name(self) -> str:
        return "Task"

    @property
    def is_readonly(self) -> bool:
        return True

    class TaskArgs(CommonToolArgs):
        description: str = Field(description="A short (3-5 word) description of the task")
        prompt: str = Field(description="The task for the agent to perform")
        agent_name: str = Field(description="The name of specialized agent to use for this task")

    args_schema: Type[BaseModel] = TaskArgs

    def _run(self, args, kwargs):
        return asyncio.run(self._arun(*args, **kwargs))

    async def _arun(self, description: str, prompt: str, agent_name: str, **kwargs) -> Any:
        """
        创建子智能体处理任务

        Args:
            description: 任务描述
            prompt: 子智能体系统提示词
            agent_name: 子智能体名称

        Yields:
            流式输出块
        """
        agent_logger.info(f"Use sub-agent to do complex task")
        self._user_canceled = False
        writer = get_stream_writer()
        context = kwargs.get("context")
        node_index = context.get("_node_index")
        if context.get("task_id") and context.get("task_id") != MAIN_AGENT_ID:
            task_id = context.get("task_id")
        else:
            # 自定义tool_start，将task_id返回去
            task_id = f"{agent_name}_{str(uuid.uuid4())}_{str(node_index)}"
            writer({
                "type": "tool_start",
                "source": context.get("agent_id"),
                "tool_id": context.get("tool_id"),
                "tool_name": self.name,
                "tool_args": {"description": description, "prompt": prompt},
                "message": "Doing...",
                "context": context,
                "task_id": task_id,
            })
        # 获取子智能体配置
        sub_agent_config = await get_sub_agent_by_name(agent_name)
        if not sub_agent_config:
            raise ValueError(f"Sub-agent {agent_name} not found")

        agent_logger.info(f"Sub-agent {agent_name} found")
        # 如果子智能体配置指定了特定工具，则过滤工具列表
        from ai_dev.utils.tool import get_available_tools, get_tools_by_names
        if sub_agent_config.tools != '*' and '*' not in sub_agent_config.tools:
            tool_names = sub_agent_config.tools if isinstance(sub_agent_config.tools, list) else [
                sub_agent_config.tools]
            sub_agent_tools = get_tools_by_names(tool_names)
        else:
            sub_agent_tools =  get_available_tools()

        # 从tool列表中去掉task，防止出现递归
        sub_agent_tools = [tool for tool in sub_agent_tools if tool.name != self.name]

        # 构建完整的系统提示词
        system_prompt = await get_sub_agent_prompt()
        agent_logger.info(f"Get system prompt success {system_prompt}")

        # 创建子智能体
        from ai_dev.core.re_act_agent import ReActAgent
        sub_agent = ReActAgent(
            name=agent_name,
            system_prompt=system_prompt,
            tools=sub_agent_tools,
            model=sub_agent_config.model
        )
        agent_logger.info(f"Create sub-agent success with name {sub_agent.name}")

        # 流式执行子智能体
        message = ((sub_agent_config.system_prompt + "\n\n" if sub_agent_config.system_prompt else "")
                   + prompt)

        last_message: BaseMessage | None = None

        async for chunk in sub_agent.run_stream(message, task_id):
            # 消息流式写出到主图去
            if chunk.get("type") in ["tool_start", "tool_delta", "tool_end"]:
                writer(chunk)

            # 然后获取工具最终结果
            if chunk.get("type") == "last_ai_message":
                # 获取最后一条消息，应该是ai消息，不是的话就报错
                last_message = chunk.get("message")

        # 处理工具的最终返回
        if self._user_canceled:
            writer({
                "type": "tool_end",
                "source": context.get("agent_id"),
                "tool_id": context.get("tool_id"),
                "tool_name": self.name,
                "task_id": task_id,
                "status": "error",
                "message": "用户取消执行",
                "context": context
            })
            return "用户取消执行"
        elif isinstance(last_message, AIMessage):
            writer({
                "type": "tool_end",
                "source": context.get("agent_id"),
                "tool_id": context.get("tool_id"),
                "tool_name": self.name,
                "task_id": task_id,
                "status": "success",
                "result": last_message.content,
                "context": context
            })
            return last_message.content
        else:
            writer({
                "type": "tool_end",
                "source": context.get("agent_id"),
                "tool_id": context.get("tool_id"),
                "tool_name": self.name,
                "task_id": task_id,
                "status": "error",
                "message": "异常:任务执行失败，未正常返回结果",
                "context": context
            })
            return "异常:任务执行失败，未正常返回结果"



