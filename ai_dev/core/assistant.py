"""
Agent管理器
"""
from typing import Optional, Any
from dotenv import load_dotenv
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from .global_state import GlobalState
from ..models.state import MyAgentState
from .re_act_agent import ReActAgent, SubAgentState
from ..constants.prompt_cn import get_system_prompt
from ..utils.logger import agent_logger
from ..utils.tool import get_available_tools
from ai_dev.constants.product import MAIN_AGENT_ID, MAIN_AGENT_NAME


class AIProgrammingAssistant:
    """AI编程助手主类"""

    def __init__(self, working_directory: str = "."):
        # 加载环境变量
        load_dotenv()

        # 初始化状态
        self.state = MyAgentState(working_directory=working_directory)

        # 延迟初始化Agent
        self.system_prompt = None
        self.main_agent: ReActAgent | None = None

    async def _initialize_agent(self):
        """延迟初始化SubAgentGraph"""
        if self.main_agent is None:
            # 获取系统提示词
            if self.system_prompt is None:
                self.system_prompt = await get_system_prompt()

            self.main_agent = ReActAgent(
                name=MAIN_AGENT_NAME,
                system_prompt=self.system_prompt,
                tools=get_available_tools(),
                context={
                    "agent_type": "main",
                    "working_directory": self.state.working_directory
                }
            )

    async def process_input_stream(self, user_input_or_resume: Any, thread_id: Optional[str] = None,
                                   resume_task_ids: list = None) -> Any:
        """流式处理用户输入"""
        try:
            # 确保SubAgentGraph已初始化
            await self._initialize_agent()

            # 构建配置参数
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "agent_id": MAIN_AGENT_ID,
                    "resume_task_ids": resume_task_ids
                },
                "recursion_limit": 1000
            }

            # 使用真正的流式输出，传递thread_id配置
            async for chunk in self.main_agent.run_stream(user_input_or_resume, MAIN_AGENT_ID, config=config):
                yield chunk


        except Exception as e:
            error_msg = f"处理过程中出现错误: {str(e)}"
            agent_logger.log_agent_error(MAIN_AGENT_ID, error_msg, e, {
                "user_input": user_input_or_resume,
                "stage": "agent_processing"
            })
            yield {"type": "error", "error": error_msg}

    async def get_agent_state(self, config) -> str:
        if self.main_agent:
            return await self.main_agent.get_graph_status(config)
        return "Finished"

    async def agent_is_running(self, config) -> bool:
        if self.main_agent:
            return await self.main_agent.graph_is_running(config)
        return False

    async def agent_is_interrupted(self, config) -> bool:
        if self.main_agent:
            return await self.main_agent.graph_is_interrupted(config)
        return False

    def reset_conversation(self):
        """重置对话"""
        self.state = MyAgentState(working_directory=self.state.working_directory)