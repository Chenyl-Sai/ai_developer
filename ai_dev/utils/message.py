import uuid

from langchain_core.messages import AnyMessage, AIMessage, SystemMessage, HumanMessage
from langgraph.config import get_stream_writer

from ai_dev.core.global_state import GlobalState
from ai_dev.utils.logger import agent_logger

INTERRUPT_MESSAGE = "[Request interrupted by user]"
INTERRUPT_MESSAGE_FOR_TOOL_USE = "[Request interrupted by user for tool use]"

AUTO_COMPACT_THRESHOLD_RATIO = 0.92

async def check_auto_compact(messages: list[AnyMessage]) -> tuple[list[AnyMessage], bool]:
    """检查是否需要压缩，如果需要则自动压缩"""
    if not should_compact(messages):
        return messages, False
    writer = get_stream_writer()

    message_id = "compact_" + str(uuid.uuid4())
    writer({
        "type": "message_start",
        "message_id": message_id
    })
    writer({
        "type": "message_delta",
        "message_id": message_id,
        "delta": "The context exceeds the threshold and compression begins…\n\n",
    })

    request_messages = [SystemMessage(
        content="You are a helpful AI assistant tasked with creating comprehensive conversation summaries that preserve all essential context for continuing development work.")]
    request_messages.extend(messages)
    request_messages.append(HumanMessage(content=COMPRESSION_PROMPT))
    model = GlobalState.get_model_manager().get_model(GlobalState.get_config_manager().get_default_model(), tags=["compact"])
    ai_message = await model.ainvoke(request_messages)
    agent_logger.info(f"Compact message finished, tokens: {count_tokens([ai_message])}")
    writer({
        "type": "message_delta",
        "message_id": message_id,
        "delta": "Context compression completed\n",
    })
    writer({
        "type": "message_end",
        "message_id": message_id
    })
    return [
        HumanMessage(content="Context automatically compressed due to token limit. Essential information preserved."),
        ai_message], True


def count_tokens(messages: list[AnyMessage]) -> int:
    for i in range(len(messages) - 1, -1, -1):
        message = messages[i]
        if isinstance(message, AIMessage) and message.usage_metadata:
            return message.usage_metadata.get("total_tokens", 0)
    return 0


def should_compact(messages: list[AnyMessage]) -> bool:
    token_count = count_tokens(messages)
    max_tokens = GlobalState.get_config_manager().get_model_config(
        GlobalState.get_config_manager().get_default_model()).get("max_context_tokens", 128000)
    auto_compact_threshold = max_tokens * AUTO_COMPACT_THRESHOLD_RATIO
    compact = token_count >= auto_compact_threshold
    if compact:
        agent_logger.info(f"Compact message detected, total tokens: {token_count}, max tokens: {max_tokens}")
    return compact


# 8步压缩法提示词
COMPRESSION_PROMPT = """Please provide a comprehensive summary of our conversation structured as follows:

## Technical Context
Development environment, tools, frameworks, and configurations in use. Programming languages, libraries, and technical constraints. File structure, directory organization, and project architecture.

## Project Overview  
Main project goals, features, and scope. Key components, modules, and their relationships. Data models, APIs, and integration patterns.

## Code Changes
Files created, modified, or analyzed during our conversation. Specific code implementations, functions, and algorithms added. Configuration changes and structural modifications.

## Debugging & Issues
Problems encountered and their root causes. Solutions implemented and their effectiveness. Error messages, logs, and diagnostic information.

## Current Status
What we just completed successfully. Current state of the codebase and any ongoing work. Test results, validation steps, and verification performed.

## Pending Tasks
Immediate next steps and priorities. Planned features, improvements, and refactoring. Known issues, technical debt, and areas needing attention.

## User Preferences
Coding style, formatting, and organizational preferences. Communication patterns and feedback style. Tool choices and workflow preferences.

## Key Decisions
Important technical decisions made and their rationale. Alternative approaches considered and why they were rejected. Trade-offs accepted and their implications.

Focus on information essential for continuing the conversation effectively, including specific details about code, files, errors, and plans."""
