import asyncio
import json
import typing

import aiofiles
import httpx
from typing import Any, Union, Dict, Optional, Callable
from pathlib import Path
from collections.abc import Mapping

from httpx import Request, Response
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
import langchain_mcp_adapters.sessions as langchain_mcp_sessions
from langchain_mcp_adapters.sessions import Connection, StdioConnection, SSEConnection, StreamableHttpConnection, \
    WebsocketConnection, McpHttpClientFactory
from langchain_mcp_adapters.tools import load_mcp_tools

from ai_dev.utils.logger import agent_logger
from ai_dev.utils.tool import tool_start_callback_handler, tool_end_callback_handler, tool_error_callback_handler


class AddHeaderAuth(httpx.Auth):

    def __init__(self, headers: dict[str, str] | None = None):
        self.headers = headers or {}

    def auth_flow(self, request: Request) -> typing.Generator[Request, Response, None]:
        for header, value in self.headers.items():
            request.headers[header] = value
        yield request

class QueryParamAuth(httpx.Auth):
    def __init__(self, params: dict[str, str] | None = None):
        self.params = params or {}

    def auth_flow(self, request: Request) -> typing.Generator[Request, Response, None]:
        params = dict(request.url.params)
        for param, value in self.params.items():
            params[param] = value
            request.url = request.url.copy_with(params=params)

        yield request


class McpClient:

    def __init__(self):
        self.mcp_http_client_factory_dict: dict[str, McpHttpClientFactory] = {}
        self.map_functional_auth_dict: dict[str, Callable[[Request], Request]] = {}
        self.multi_server_mcp_client: MultiServerMCPClient | None = None
        self.server_tools: dict[str, list[BaseTool]] = {}
        langchain_mcp_sessions._create_stdio_session = _create_stdio_session


    async def initialize(self):
        if self.multi_server_mcp_client is None:
            # 解析配置文件
            from ai_dev.core.global_state import GlobalState
            user_dir = Path.home() / ".ai_dev" / "mcp"
            project_dir = Path(GlobalState.get_working_directory()) / ".ai_dev" / "mcp"
            load_mcp_config_tasks =  [self._scan_mcp_directory(user_dir),
                                      self._scan_mcp_directory(project_dir)]
            (users_connections, projects_connections) = await asyncio.gather(*load_mcp_config_tasks)
            all_connections = {}
            for name, connection in users_connections.items():
                all_connections.update({name: connection})
            for name, connection in projects_connections.items():
                all_connections.update({name: connection})
            # 初始化client
            self.multi_server_mcp_client = MultiServerMCPClient(all_connections)

    async def get_tools(self, server_name: str | None = None) -> list[BaseTool]:
        if not self.multi_server_mcp_client:
            return []

        if server_name is None:
            if not self.server_tools:
                load_mcp_tool_tasks = []
                server_names = []
                for server_name, connection in self.multi_server_mcp_client.connections.items():
                    load_mcp_tool_task = asyncio.create_task(
                        load_mcp_tools(None, connection=connection)
                    )
                    load_mcp_tool_tasks.append(load_mcp_tool_task)
                    server_names.append(server_name)
                tools_list = await asyncio.gather(*load_mcp_tool_tasks)
                for tools, server_name in zip(tools_list, server_names):
                    if tools:
                        for tool in tools:
                            tool.name = f"mcp__{server_name}__{tool.name}"
                            tool.callbacks = [tool_start_callback_handler, tool_end_callback_handler,
                                              tool_error_callback_handler]
                    else:
                        tools = []
                    self.server_tools.update({server_name: tools})
            return [tool for tools in self.server_tools.values() for tool in tools]
        else:
            if not self.server_tools.get(server_name):
                tools= await self.multi_server_mcp_client.get_tools(server_name=server_name)
                if tools:
                    for tool in tools:
                        tool.name = f"mcp__{server_name}__{tool.name}"
                        tool.callbacks = [tool_start_callback_handler, tool_end_callback_handler,
                                          tool_error_callback_handler]
                self.server_tools.update({server_name: tools})
            return self.server_tools.get(server_name)

    def register_http_clint_factory(self, name: str, factory: McpHttpClientFactory) -> None:
        self.mcp_http_client_factory_dict.update({name: factory})

    def register_functional_auth(self, name: str, func: Callable[[Request], Request]) -> None:
        self.map_functional_auth_dict.update({name: func})

    def get_registered_http_clint_factory(self, name: str) -> Optional[McpHttpClientFactory]:
        return self.mcp_http_client_factory_dict.get(name)

    def get_registered_functional_auth(self, name: str) -> Optional[Callable[[Request], Request]]:
        return self.map_functional_auth_dict.get(name)

    async def _scan_mcp_directory(self, directory: Path) -> dict[str, Connection]:
        agent_logger.debug(f"Load mcp from {directory}")
        if not directory.exists():
            return {}
        connections: dict[str, Connection] = {}
        for file in directory.iterdir():
            if file.is_dir():
                continue
            if file.suffix != '.json' or file.name == 'mcp_example.json':
                continue
            try:
                async with aiofiles.open(file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    mcp_config = json.loads(content)
                    if "mcpServers" not in mcp_config:
                        continue
                    mcp_servers = mcp_config.get("mcpServers")
                    if isinstance(mcp_servers, Mapping):
                        for server_name, server_config in mcp_servers.items():
                            agent_logger.debug(f"Load {server_name}")
                            try:
                                if "transport" not in server_config:
                                    raise ValueError(f"No transport configuration")
                                elif server_config["transport"] == "stdio":
                                    connections[server_name] = self._parse_stdio_config(server_config)
                                elif server_config["transport"] == "sse":
                                    connections[server_name] = self._parse_sse_config(server_config)
                                elif server_config["transport"] == "streamable_http":
                                    connections[server_name] = self._parse_streamable_http_config(server_config)
                                elif server_config["transport"] == "websocket":
                                    connections[server_name] = self._parse_websocket_config(server_config)
                                else:
                                    raise ValueError(f"Invalid transport {server_config['transport']}")
                            except ValueError as e:
                                agent_logger.error(f"Failed parse config for server {server_name} in {file}", exception=e)
            except Exception as e:
                agent_logger.error(f"Failed to parse mcp config for file {file}", exception=e)

        agent_logger.debug(f"Load from {directory} finished: {connections}")
        return connections

    def _parse_stdio_config(self, stdio_config: dict[str, Any]) -> StdioConnection:
        """处理stdio格式的配置"""
        # 必传
        command = stdio_config.get("command")
        if not command:
            raise ValueError("No 'command' specified")
        args = stdio_config.get("args")
        if not isinstance(args, list):
            raise ValueError("'args' must be a list")
        if not args:
            raise ValueError("No 'args' specified")

        return StdioConnection(**stdio_config)

    def _parse_sse_config(self, sse_config: dict[str, Any]) -> SSEConnection:
        """处理SSE格式的配置"""
        # 必传参数
        url = sse_config.get("url")
        if not url:
            raise ValueError("No 'url' specified for SSE connection")
        
        # 可选参数
        config = {
            "url": url,
            "headers": sse_config.get("headers"),
            "timeout": sse_config.get("timeout"),
            "sse_read_timeout": sse_config.get("sse_read_timeout"),
            "session_kwargs": sse_config.get("session_kwargs"),
        }
        
        # 处理httpx_client_factory
        factory_name = sse_config.get("httpx_client_factory")
        if factory_name:
            config["httpx_client_factory"] = self.get_registered_http_clint_factory(factory_name)
        
        # 处理auth
        auth_config = sse_config.get("auth")
        if auth_config:
            config["auth"] = self._create_auth(auth_config)
        
        # 过滤掉None值
        config = {k: v for k, v in config.items() if v is not None}
        
        return SSEConnection(**config)

    def _parse_streamable_http_config(self, streamable_http_config: dict[str, Any]) -> StreamableHttpConnection:
        """处理Streamable HTTP格式的配置"""
        # 必传参数
        url = streamable_http_config.get("url")
        if not url:
            raise ValueError("No 'url' specified for Streamable HTTP connection")
        
        # 可选参数
        config = {
            "url": url,
            "headers": streamable_http_config.get("headers"),
            "timeout": streamable_http_config.get("timeout"),
            "sse_read_timeout": streamable_http_config.get("sse_read_timeout"),
            "terminate_on_close": streamable_http_config.get("terminate_on_close"),
            "session_kwargs": streamable_http_config.get("session_kwargs"),
        }
        
        # 处理httpx_client_factory
        factory_name = streamable_http_config.get("httpx_client_factory")
        if factory_name:
            config["httpx_client_factory"] = self.get_registered_http_clint_factory(factory_name)

        # 处理auth
        auth_config = streamable_http_config.get("auth")
        if auth_config:
            config["auth"] = self._create_auth(auth_config)
        
        # 过滤掉None值
        config = {k: v for k, v in config.items() if v is not None}
        
        return StreamableHttpConnection(**config)

    def _parse_websocket_config(self, websocket_config: dict[str, Any]) -> WebsocketConnection:
        """处理WebSocket格式的配置"""
        # 必传参数
        url = websocket_config.get("url")
        if not url:
            raise ValueError("No 'url' specified for WebSocket connection")
        
        # 可选参数
        config = {
            "url": url,
            "session_kwargs": websocket_config.get("session_kwargs")
        }
        
        # 过滤掉None值
        config = {k: v for k, v in config.items() if v is not None}
        
        return WebsocketConnection(**config)

    def _create_auth(self, auth_config: Union[Dict[str, Any], str, None]) -> httpx.Auth | None:
        """根据配置创建认证对象"""

        if auth_config is None:
            return None

        # 如果已经是Auth对象（在动态加载时可能）
        if isinstance(auth_config, httpx.Auth):
            return auth_config

        # 字典格式：支持多种认证类型
        if isinstance(auth_config, dict):
            auth_type = auth_config.get('type')
            if auth_type == 'bearer':
                token = auth_config.get('token')
                if not token:
                    raise ValueError("Bearer auth requires 'token'")
                return AddHeaderAuth({"Authorization": f"Bearer {token}"})

            elif auth_type == 'basic':
                username = auth_config.get('username')
                password = auth_config.get('password')
                if not username or not password:
                    raise ValueError("Basic auth requires 'username' and 'password'")
                return httpx.BasicAuth(username, password)

            elif auth_type == 'digest':
                username = auth_config.get('username')
                password = auth_config.get('password')
                if not username or not password:
                    raise ValueError("Basic auth requires 'username' and 'password'")
                return httpx.DigestAuth(username, password)

            elif auth_type == 'api_key':
                api_key = auth_config.get('api_key')
                if not api_key:
                    raise ValueError("Api_Key auth requires 'api_key'")
                param_name = auth_config.get('param_name', 'Authorization')
                param_in = auth_config.get('param_in', 'header')  # header or query

                if param_in == 'header':
                    return AddHeaderAuth({param_name: api_key})
                else:
                    return QueryParamAuth({param_name: api_key})
            elif auth_type == 'func':
                func_name = auth_config.get('func_name')
                if not func_name:
                    raise ValueError("Function auth requires 'func_name'")
                func = self.get_registered_functional_auth(func_name)
                if not func:
                    raise ValueError(f"Function name {func_name} not found, "
                                     f"please use McpClient.register_functional_auth() to register functional auth")
                return httpx.FunctionAuth(func)

            else:
                raise ValueError(f"Unsupported auth type: {auth_type}")

        return None


############################这里重新实现langchain-mcp-adapters.sessions._create_stdio_session方法#############################
"""
在使用stdio_client启动MCP Server的时候，源码中没有传递errlog参数，
默认的参数会将Server的输出日志直接输出到用户交互界面中
这里修改参数，直接传递subprocess.DEVNULL，忽略Server输出的日志
"""
from typing import Literal
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from langchain_mcp_adapters.sessions import DEFAULT_ENCODING, DEFAULT_ENCODING_ERROR_HANDLER
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

@asynccontextmanager
async def _create_stdio_session(  # noqa: PLR0913
        *,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        encoding: str = DEFAULT_ENCODING,
        encoding_error_handler: Literal[
            "strict", "ignore", "replace"
        ] = DEFAULT_ENCODING_ERROR_HANDLER,
        session_kwargs: dict[str, Any] | None = None,
) -> AsyncIterator[ClientSession]:
    """Create a new session to an MCP server using stdio.

    Args:
        command: Command to execute.
        args: Arguments for the command.
        env: Environment variables for the command.
            If not specified, inherits a subset of the current environment.
            The details are implemented in the MCP sdk.
        cwd: Working directory for the command.
        encoding: Character encoding.
        encoding_error_handler: How to handle encoding errors.
        session_kwargs: Additional keyword arguments to pass to the ClientSession.

    Yields:
        An initialized ClientSession.
    """
    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env,
        cwd=cwd,
        encoding=encoding,
        encoding_error_handler=encoding_error_handler,
    )

    # Create and store the connection
    import subprocess
    async with (
        stdio_client(server_params, subprocess.DEVNULL) as (read, write),
        ClientSession(read, write, **(session_kwargs or {})) as session,
    ):
        yield session

mcp_client = McpClient()