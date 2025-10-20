from langchain_core.messages import AnyMessage, AIMessage, SystemMessage, HumanMessage, AIMessageChunk

from ai_dev.utils.logger import agent_logger


def count_tokens(messages: list[AnyMessage]) -> int:
    for i in range(len(messages) - 1, -1, -1):
        message = messages[i]
        if isinstance(message, AIMessage) and message.usage_metadata:
            return message.usage_metadata.get("total_tokens", 0)
    return 0

def estimate_token_for_chunk_message(message: AIMessageChunk) -> float:
    content_tokens = 0
    tool_call_tokens = 0
    try:
        if message.content:
            content = message.content
            chinese_chars = sum(1 for char in content if '\u4e00' <= char <= '\u9fff')
            english_chars = len(content) - chinese_chars
            content_tokens = int(chinese_chars * 1.5 + english_chars * 0.25)

        if message.additional_kwargs and message.additional_kwargs.get("tool_calls"):
            for tool_call in message.additional_kwargs.get("tool_calls", []):
                func = tool_call.get("function", {})
                if func:
                    arguments = func.get("arguments", "")
                    name = func.get("name", "")
                    total = arguments if arguments else "" + name if name else ""
                    tool_chinese_chars = sum(1 for char in total if '\u4e00' <= char <= '\u9fff')
                    tool_english_chars = len(total) - tool_chinese_chars
                    tool_call_tokens += tool_chinese_chars * 1.5 + tool_english_chars * 0.25
    except Exception as e:
        agent_logger.error("estimate token error", exception=e, context={"message": message})
        pass

    return content_tokens + tool_call_tokens
