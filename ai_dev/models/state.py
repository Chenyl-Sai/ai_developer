"""
Agent状态模型定义
"""

from typing import List, Dict, Any, Optional, Union, Annotated
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage, AnyMessage
from langgraph.graph import add_messages


class AgentState(BaseModel):
    """Agent状态"""
    # 对话历史 - 使用LangChain的Message类型
    messages: Annotated[list, add_messages] = Field(default=[])

    # 当前用户输入
    user_input: str = ""

    # 工具执行结果
    tool_results: List[ToolMessage] = Field(default_factory=list)

    # 系统状态
    working_directory: str = "."
    environment_info: Dict[str, Any] = Field(default_factory=dict)

    # 控制状态
    should_continue: bool = True
    max_tool_calls: int = 10
    current_tool_calls: int = 0

    # 错误信息
    error: Optional[str] = None


class EnvironmentState(BaseModel):
    """环境状态"""
    working_directory: str
    files: List[str] = Field(default_factory=list)
    git_info: Optional[Dict[str, Any]] = None
    system_info: Dict[str, Any] = Field(default_factory=dict)