"""
工具基类定义
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, Generator, Annotated
from pathlib import Path
import os
import json
from pydantic import BaseModel
from langchain_core.tools import BaseTool as LangChainBaseTool, InjectedToolArg
from langgraph.config import get_stream_writer
from ai_dev.core.global_state import GlobalState
from ai_dev.utils.logger import agent_logger

class CommonToolArgs(BaseModel):
    context: Annotated[dict, InjectedToolArg]

class BaseTool(LangChainBaseTool, ABC):
    """工具基类 - 继承自LangChain的BaseTool"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def show_name(self) -> str:
        """工具显示名称"""
        return self.__class__.__name__

    @property
    def is_available(self) -> bool:
        """工具是否可用"""
        return True

    @property
    def is_readonly(self) -> bool:
        """工具是否只读"""
        return False

    @property
    def is_parallelizable(self) -> bool:
        """工具是否可并行执行"""
        return False

    def get_tool_info(self) -> Dict[str, Any]:
        """获取工具完整信息"""
        return {
            "name": self.name,
            "description": self.description,
            "is_available": self.is_available,
            "is_readonly": self.is_readonly,
            "is_parallelizable": self.is_parallelizable,
            "args_schema": self.args_schema
        }

    def _validate_path(self, path: str) -> Path:
        """验证路径安全性"""
        abs_path = Path(path).resolve()

        # 检查是否在允许的路径内
        if not str(abs_path).startswith(GlobalState.get_working_directory()):
            raise PermissionError(f"Access denied: {path} is outside working directory")

        return abs_path

    def _safe_join_path(self, *paths) -> Path:
        """安全地拼接路径"""
        if paths:
            first_path = Path(paths[0])
            # 如果第一个路径是绝对路径，直接使用
            if first_path.is_absolute():
                joined = first_path.resolve()
                # 如果有多个路径，拼接剩余部分
                if len(paths) > 1:
                    joined = joined.joinpath(*paths[1:]).resolve()
            else:
                # 如果是相对路径，拼接工作目录
                joined = Path(GlobalState.get_working_directory()).joinpath(*paths).resolve()
        else:
            joined = Path(GlobalState.get_working_directory()).resolve()

        return self._validate_path(str(joined))

    def need_permission(self, **kwargs) -> bool:
        """检查工具执行是否需要权限"""
        # 只读工具默认不需要权限检查
        if self.is_readonly:
            return False

        # 其他工具需要权限检查
        return True

class StreamTool(BaseTool):
    """支持流式输出的工具基类"""

    def _run(self, *args, **kwargs) -> str:
        """
        执行工具 - 自动处理流式输出

        流式执行阶段：
        1. 开始执行：显示工具调用信息
        2. 执行中：显示进度状态
        3. 完成/失败：显示最终结果
        """
        writer = get_stream_writer()
        context = kwargs.get("context", {})
        # 阶段1: 开始执行
        if self._send_tool_start_event():
            writer({
                "type": "tool_start",
                "tool_id": context.get("tool_id"),
                "tool_name": self.name,
                "tool_args": kwargs,
                "shown_tool_args": self._format_args(kwargs),
                "title": f"<b>{self.show_name}</b>({self._format_args(kwargs)})",
                "message": "Doing...",
                "context": context
            })

        try:
            # 执行工具逻辑 - 支持生成器返回
            llm_result = ""
            for result in self._execute_tool(*args, **kwargs):
                # 处理新的字典格式
                if result["type"] == "tool_delta":
                    # 进度信息直接显示给用户
                    writer({
                        "type": "tool_delta",
                        "tool_id": context.get("tool_id"),
                        "tool_name": self.name,
                        "message": result.get("show_message", ""),
                        "context": context
                    })
                elif result["type"] == "tool_end":
                    # 最终结果
                    llm_result = result.get("result_for_llm", "")
                    # 阶段2: 执行完成
                    writer({
                        "type": "tool_end",
                        "tool_id": context.get("tool_id"),
                        "tool_name": self.name,
                        "message": f"{self._get_success_message(llm_result)}",
                        "status": "success",
                        "result": llm_result,
                        "context": context
                    })

            return llm_result

        except Exception as e:
            # 阶段2: 执行失败
            writer({
                "type": "tool_end",
                "tool_id": context.get("tool_id"),
                "tool_name": self.name,
                "message": str(e),
                "status": "error",
                "context": context
            })
            raise e

    def _send_tool_start_event(self):
        """"是否发送工具开始执行事件"""
        return True

    def _execute_tool(self, *args, **kwargs) -> Any:
        """
        执行工具逻辑 - 子类需要重写此方法

        返回工具执行结果（字符串形式）
        """
        raise NotImplementedError("Subclasses must implement _execute_tool method")

    def _format_args(self, kwargs: Dict[str, Any]) -> str:
        """格式化工具参数用于显示"""
        args_str = ", ".join([f"{k}: {repr(v)}" for k, v in kwargs.items() if k not in ["context"]])
        return args_str

    def _get_success_message(self, llm_result) -> str:
        """生成成功消息"""
        # 子类可以重写此方法提供更具体的成功消息
        return f"成功执行"