import asyncio
from typing import Any, Annotated
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.config import get_stream_writer
from langchain_core.tools import BaseTool, InjectedToolArg
from pydantic import BaseModel

from ai_dev.utils.logger import agent_logger


class CommonToolArgs(BaseModel):
    context: Annotated[dict, InjectedToolArg]


_all_tools = []


async def get_all_tools() -> list[BaseTool]:
    from ai_dev.tools import (FileReadTool, FileEditTool, FileWriteTool, FileListTool, GrepTool, GlobTool,
                              TodoWriteTool, TaskTool, BashExecuteTool)
    from .mcp import mcp_client

    if not _all_tools:
        file_read_tool = FileReadTool()
        file_edit_tool = FileEditTool()
        file_write_tool = FileWriteTool()
        file_list_tool = FileListTool()
        glob_tool = GrepTool()
        grep_tool = GrepTool()
        task_tool = TaskTool()
        todo_write_tool = TodoWriteTool()
        bash_execute_tool = BashExecuteTool()

        _all_tools.extend([file_read_tool,
                           file_edit_tool,
                           file_write_tool,
                           file_list_tool,
                           glob_tool,
                           grep_tool,
                           task_tool,
                           todo_write_tool,
                           bash_execute_tool
                           ])

    mcp_tools = await mcp_client.get_tools()
    agent_logger.info(f"Found {len(mcp_tools)} mcp tools")
    if mcp_tools:
        return _all_tools + mcp_tools
    else:
        return _all_tools


async def get_tool_by_name(name: str) -> BaseTool:
    return next(filter(lambda tool: tool.name == name, await get_all_tools()), None)


async def get_tools_by_names(names: list[str]) -> list[BaseTool]:
    return [tool for tool in await get_all_tools() if tool.name in names]


run_id_info_cache: dict[str, Any] = {}


class ToolStartCallbackHandler(BaseCallbackHandler):
    def on_tool_start(
            self,
            serialized: dict[str, Any],
            input_str: str,
            *,
            run_id: UUID,
            parent_run_id: UUID | None = None,
            tags: list[str] | None = None,
            metadata: dict[str, Any] | None = None,
            inputs: dict[str, Any] | None = None,
            **kwargs: Any, ):
        run_id_info_cache.update({
            str(run_id): {
                "context": inputs.get("context"),
                "tool_id": inputs.get("context").get("tool_id"),
                "tool_name": serialized.get("name"),
            }})
        writer = get_stream_writer()
        writer({
            "type": "tool_start",
            "source": inputs.get("context").get("agent_id"),
            "tool_id": inputs.get("context").get("tool_id"),
            "tool_name": serialized.get("name"),
            "tool_args": inputs,
            "message": "Doing...",
        })


class ToolEndCallbackHandler(BaseCallbackHandler):
    def on_tool_end(
            self,
            output: Any,
            *,
            run_id: UUID,
            parent_run_id: UUID | None = None,
            **kwargs: Any,
    ) -> Any:
        info = run_id_info_cache.get(str(run_id))
        if info:
            context = info.get("context", {})
            source = context.get("agent_id")
            tool_id = info.get("tool_id")
            if source and tool_id:
                writer = get_stream_writer()
                writer({
                    "type": "tool_end",
                    "source": source,
                    "tool_id": output.tool_call_id,
                    "tool_name": info.get("tool_name"),
                    "status": "success",
                    "result": output.artifact if output.artifact else output.content,
                    "context": context
                })
            try:
                del run_id_info_cache[str(run_id)]
            except:
                pass


class ToolErrorCallbackHandler(BaseCallbackHandler):
    def on_tool_error(
            self,
            error: BaseException,
            *,
            run_id: UUID,
            parent_run_id: UUID | None = None,
            **kwargs: Any,
    ) -> Any:
        info = run_id_info_cache.get(str(run_id))
        if info:
            context = info.get("context", {})
            source = context.get("agent_id")
            tool_id = info.get("tool_id")
            if source and tool_id:
                writer = get_stream_writer()
                writer({
                    "type": "tool_end",
                    "source": source,
                    "tool_id": tool_id,
                    "tool_name": info.get("tool_name"),
                    "message": str(error),
                    "status": "error",
                    "context": context
                })
            try:
                del run_id_info_cache[str(run_id)]
            except:
                pass


tool_start_callback_handler = ToolStartCallbackHandler()
tool_end_callback_handler = ToolEndCallbackHandler()
tool_error_callback_handler = ToolErrorCallbackHandler()
