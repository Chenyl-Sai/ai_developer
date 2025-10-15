"""
流式输出处理器 - 统一处理子代理的流式输出
"""

from typing import Dict, Any, AsyncGenerator
from ..utils.logger import agent_logger


class StreamProcessor:
    """流式输出处理器"""

    @staticmethod
    async def process_sub_agent_stream(stream_generator: AsyncGenerator, agent_name: str = None
                                       ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理子代理的流式输出

        Args:
            stream_generator: 子代理的流式生成器
            agent_name: 代理名称（可选）

        Yields:
            处理后的流式输出块
        """
        full_response = ""

        async for chunk in stream_generator:
            chunk_type = chunk.get("type")

            # 处理文本块
            if chunk_type == "text_chunk":
                content = chunk["content"]
                # 只有当content不为空时才处理，避免累积空内容
                if content:
                    full_response += content
                    yield {
                        "type": "text_chunk",
                        "content": content,
                        "full_response": full_response,
                        **({"agent_name": agent_name} if agent_name else {})
                    }

            # 模型单次回单完成,清空拼接数据
            if chunk_type == "llm_finish":
                full_response = ""
                yield {
                    "type": "llm_finish",
                    "content": "",
                    "full_response": full_response
                }

            # 处理工具调用
            elif chunk_type == "tool_call":
                yield {
                    "type": "tool_call",
                    "tool_name": chunk.get("tool_name"),
                    "tool_args": chunk.get("tool_args", {}),
                    "tool_id": chunk.get("tool_id", ""),
                    **({"agent_name": agent_name} if agent_name else {})
                }

            # 处理工具结果
            elif chunk_type == "tool_result":
                if agent_name:
                    agent_logger.log_tool_result(agent_name, chunk["tool_name"], chunk["result"], True)
                yield {
                    "type": "tool_result",
                    "tool_name": chunk["tool_name"],
                    "result": chunk["result"],
                    "success": True,
                    **({"agent_name": agent_name} if agent_name else {})
                }

            # 处理工具开始执行
            elif chunk_type == "tool_start":
                yield {
                    "type": "tool_start",
                    "tool_name": chunk.get("tool_name"),
                    "tool_args": chunk.get("tool_args", {}),
                    "title": chunk.get("title", ""),
                    "message": chunk.get("message", ""),
                    **({"agent_name": agent_name} if agent_name else {})
                }

            # 处理工具执行完成
            elif chunk_type == "tool_complete":
                yield {
                    "type": "tool_complete",
                    "tool_name": chunk.get("tool_name"),
                    "message": chunk.get("message", ""),
                    "status": chunk.get("status", "success"),
                    "result": chunk.get("result"),
                    **({"agent_name": agent_name} if agent_name else {})
                }

            # 处理工具进度更新
            elif chunk_type == "tool_progress":
                yield {
                    "type": "tool_progress",
                    "tool_name": chunk.get("tool_name"),
                    "message": chunk.get("message", ""),
                    "status": chunk.get("status", "progress"),
                    **({"agent_name": agent_name} if agent_name else {})
                }

            # 处理自定义输出
            elif chunk_type == "custom":
                yield {
                    "type": "custom",
                    "content": chunk.get("content"),
                    **({"agent_name": agent_name} if agent_name else {})
                }

            # 处理权限请求中断
            elif chunk_type == "permission_request":
                yield {
                    "type": "permission_request",
                    "interrupt_info": chunk.get("interrupt_info", {}),
                    "message": chunk.get("message", "需要权限确认"),
                    **({"agent_name": agent_name} if agent_name else {})
                }

            # 处理权限请求中断
            elif chunk_type == "wait_input":
                yield {
                    "type": "wait_input",
                    "interrupt_info": chunk.get("interrupt_info", {}),
                    "message": chunk.get("message", "等待输入"),
                    **({"agent_name": agent_name} if agent_name else {})
                }

            # 处理完成信号
            elif chunk_type == "complete":
                full_response = chunk["full_response"]

                yield {
                    "type": "complete",
                    "full_response": full_response,
                    **({"agent_name": agent_name} if agent_name else {})
                }
                break

            # 处理未知类型
            else:
                yield {
                    "type": "unknown",
                    "content": chunk,
                    **({"agent_name": agent_name} if agent_name else {})
                }