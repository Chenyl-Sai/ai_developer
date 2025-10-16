"""
TaskTool - 用于创建子智能体的工具
"""

import json, asyncio, uuid
from typing import Any, Dict, Type, Generator
from datetime import datetime

from .base import BaseTool
from ..constants.prompt import get_sub_agent_prompt
from ..core.re_act_agent import ReActAgent
from ..utils.subagent import get_sub_agent_by_name, get_agent_descriptions
from ..utils.stream_processor import StreamProcessor
from ..core.global_state import GlobalState
from pydantic import BaseModel, Field
from langgraph.config import get_stream_writer


class TaskTool(BaseTool):
    """任务工具 - 用于创建子智能体处理复杂任务"""

    # LangChain BaseTool要求的属性
    name: str = "TaskTool"
    description: str = f"""Launch a new agent to handle complex, multi-step tasks autonomously. 

Available agent types and the tools they have access to:
{asyncio.run(get_agent_descriptions())}

When using the Task tool, you must specify a subagent_type parameter to select which agent type to use.

When to use the Agent tool:
- When you are instructed to execute custom slash commands. Use the Agent tool with the slash command invocation as the entire prompt. The slash command can take arguments. For example: Task(description="Check the file", prompt="/check-file path/to/file.py")

When NOT to use the Agent tool:
- If you want to read a specific file path, use the FileReadTool or GlobTool tool instead of the Agent tool, to find the match more quickly
- If you are searching for a specific class definition like "class Foo", use the GlobTool tool instead, to find the match more quickly
- If you are searching for code within a specific file or set of 2-3 files, use the FileReadTool tool instead of the Agent tool, to find the match more quickly
- Other tasks that are not related to the agent descriptions above

Usage notes:
1. Launch multiple agents concurrently whenever possible, to maximize performance; to do that, use a single message with multiple tool uses
2. When the agent is done, it will return a single message back to you. The result returned by the agent is not visible to the user. To show the user the result, you should send a text message back to the user with a concise summary of the result.
3. Each agent invocation is stateless. You will not be able to send additional messages to the agent, nor will the agent be able to communicate with you outside of its final report. Therefore, your prompt should contain a highly detailed task description for the agent to perform autonomously and you should specify exactly what information the agent should return back to you in its final and only message to you.
4. The agent's outputs should generally be trusted
5. Clearly tell the agent whether you expect it to write code or just to do research (search, file reads, web fetches, etc.), since it is not aware of the user's intent
6. If the agent description mentions that it should be used proactively, then you should try your best to use it without the user having to ask for it first. Use your judgement.

Example usage:

<example_agent_descriptions>
"code-reviewer": use this agent after you are done writing a signficant piece of code
"greeting-responder": use this agent when to respond to user greetings with a friendly joke
</example_agent_description>

<example>
user: "Please write a function that checks if a number is prime"
assistant: Sure let me write a function that checks if a number is prime
assistant: First let me use the FileWriteTool tool to write a function that checks if a number is prime
assistant: I'm going to use the FileWriteTool tool to write the following code:
<code>
def is_prime(n):
    if n <= 1:
        return False
    for i in range(2, n):
        if n % i == 0:
            return False
    return True
</code>
<commentary>
Since a signficant piece of code was written and the task was completed, now use the code-reviewer agent to review the code
</commentary>
assistant: Now let me use the code-reviewer agent to review the code
assistant: Uses the Task tool to launch the with the code-reviewer agent 
</example>

<example>
user: "Hello"
<commentary>
Since the user is greeting, use the greeting-responder agent to respond with a friendly joke
</commentary>
assistant: "I'm going to use the Task tool to launch the with the greeting-responder agent"
</example>"""

    @property
    def show_name(self) -> str:
        return "Task"

    @property
    def is_readonly(self) -> bool:
        return True

    class TaskArgs(BaseModel):
        description: str = Field(description="A short (3-5 word) description of the task")
        prompt: str = Field(description="The task for the agent to perform")
        agent_name: str = Field(description="The name of specialized agent to use for this task")

    args_schema: Type[BaseModel] = TaskArgs

    async def _run(self, description: str, prompt: str, agent_name: str):
        """
        创建子智能体处理任务

        Args:
            description: 任务描述
            prompt: 子智能体系统提示词
            agent_name: 子智能体名称

        Yields:
            流式输出块
        """
        writer = get_stream_writer()
        # 获取子智能体配置
        sub_agent_config = await get_sub_agent_by_name(agent_name)
        if not sub_agent_config:
            raise ValueError(f"Sub-agent {agent_name} not found")

        # 如果子智能体配置指定了特定工具，则过滤工具列表
        from ..utils.tool import get_available_tools, get_tools_by_names
        if sub_agent_config.tools != '*' and '*' not in sub_agent_config.tools:
            tool_names = sub_agent_config.tools if isinstance(sub_agent_config.tools, list) else [
                sub_agent_config.tools]
            sub_agent_tools = await get_tools_by_names(tool_names)
        else:
            sub_agent_tools =  await get_available_tools()

        # 从tool列表中去掉task，防止出现递归
        sub_agent_tools = [tool for tool in sub_agent_tools if tool.name != TaskTool.name]

        # 构建完整的系统提示词
        system_prompt = await get_sub_agent_prompt()

        # 创建子智能体
        sub_agent = ReActAgent(
            system_prompt=system_prompt,
            tools=sub_agent_tools,
            model=sub_agent_config.model,
            context={
                "parent_task": description,
                "agent_config": sub_agent_config.dict(),
                "created_at": datetime.now().isoformat()
            }
        )

        # 流式执行子智能体
        message = ((sub_agent_config.system_prompt + "\n\n" if sub_agent_config.system_prompt else "")
                   + prompt)

        config = {
            "configurable": {
                "thread_id": str(uuid.uuid4()),
                "agent_id": sub_agent_config.agent_name + str(uuid.uuid4()),
            },
            "recursion_limit": 1000,
        }

        async for chunk in StreamProcessor.process_sub_agent_stream(
            sub_agent.run_stream(message, config),
            agent_name=agent_name
        ):
            writer(chunk)

        return "Task finish success"

