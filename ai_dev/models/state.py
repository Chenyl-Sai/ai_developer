"""
Agent状态模型定义
"""

from typing import List, Dict, Any, Optional, Union, Annotated, Literal
from pydantic import BaseModel, Field
from langchain_core.messages.utils import MessageLikeRepresentation
from langgraph.graph import add_messages

Messages = Union[list[MessageLikeRepresentation], MessageLikeRepresentation]


def add_or_replace_messages(left: Messages,
                            right: Messages) -> Messages:
    """用来处理压缩消息之后需要替换掉原先messages列表的情况"""
    if isinstance(right, dict) and "messages" in right and "_replace" in right:
        return right.get("messages")
    else:
        return add_messages(left, right)


def accept_new_merger(old_value:bool, new_value:bool) -> bool:
    return new_value

class MyAgentState(BaseModel):
    """Agent状态"""
    # 对话历史 - 使用LangChain的Message类型
    messages: Annotated[list, add_or_replace_messages] = Field(default=[])

    # 当前用户输入
    user_input: str = ""

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
