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
                        **chunk,
                        "full_response": full_response,
                        **({"agent_name": agent_name} if agent_name else {})
                    }
            # 模型单次回单完成,清空拼接数据
            elif chunk_type == "llm_finish":
                full_response = ""
                yield {
                    **chunk,
                    "full_response": ""
                }
            else:
                yield {
                    **chunk,
                    **({"agent_name": agent_name} if agent_name else {})
                }