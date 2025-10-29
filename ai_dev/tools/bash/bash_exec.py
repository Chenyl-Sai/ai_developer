"""
Bash 执行工具 - 支持异步执行、回调机制和命令队列
"""

import asyncio
import subprocess
from typing import Any, Dict, Optional, Callable, Type, Generator, AsyncGenerator

from langchain_core.callbacks import Callbacks
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from ai_dev.utils.tool import CommonToolArgs
from ai_dev.utils.bash_executor import (
    BashExecutor,
    CommandResult,
    CommandStatus,
    get_bash_executor
)
from ai_dev.core.global_state import GlobalState
from .prompt_cn import prompt
from ...utils.logger import agent_logger
from ...utils.tool import tool_start_callback_handler, tool_end_callback_handler, tool_error_callback_handler


class BashExecuteArgs(CommonToolArgs):
    """Bash 执行工具参数"""
    command: str = Field(..., description="The command to execute")
    propose: str = Field(description="Briefly explain the intention of the bash script executed this time")
    timeout: Optional[int] = Field(default=None, description="Optional timeout in seconds (max 600)")

class BashExecuteTool(BaseTool):
    """Bash 执行工具"""

    name: str = "BashExecuteTool"
    description: str = prompt
    response_format: str = "content_and_artifact"
    args_schema: Type[BaseModel] = BashExecuteArgs

    callbacks: Callbacks = [tool_start_callback_handler, tool_end_callback_handler, tool_error_callback_handler]

    # 全局执行器实例
    _executor: Optional[BashExecutor] = None

    @property
    def executor(self) -> BashExecutor:
        """获取执行器实例"""
        if self._executor is None:
            self._executor = BashExecutor()
            self._executor.start_queue_processor()
        return self._executor

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        """执行工具逻辑 - 同步等待命令完成并返回结果"""
        args = BashExecuteArgs(**kwargs)

        # 验证工作目录
        working_dir = GlobalState.get_working_directory()

        # 都直接执行
        use_queue = False
        if use_queue:
            # 对于队列执行，使用队列处理器
            result_data = asyncio.run(self._execute_with_queue(args, working_dir))
        else:
            # 对于直接执行，直接运行命令
            result_data = self._execute_direct(args, working_dir)
        return result_data, {}

    def _execute_direct(self, args: BashExecuteArgs, working_dir: str) -> Dict[str, Any]:
        """直接执行命令"""
        try:
            import time
            start_time = time.time()

            # 直接执行命令
            result = self._run_command_sync(
                args.command,
                working_dir,
                args.timeout
            )

            execution_time = time.time() - start_time
            command_result = CommandResult(
                command_id="direct_exec",
                command=args.command,
                status=CommandStatus.COMPLETED,
                return_code=result["return_code"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                execution_time=execution_time
            )

            return self._format_command_result(command_result)

        except Exception as e:
            return {
                "status": "failed",
                "return_code": -1,
                "stdout": "",
                "stderr": "",
                "execution_time": 0.0,
                "error_message": f"命令执行失败: {str(e)}"
            }

    def _run_command_sync(self, command: str, working_directory: str, timeout: Optional[int]) -> Dict[str, Any]:
        """同步执行命令"""
        try:
            process = subprocess.run(
                command,
                shell=True,
                cwd=working_directory,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            return {
                "return_code": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr
            }

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Command timed out after {timeout} seconds")
        except Exception as e:
            raise RuntimeError(f"Command execution failed: {e}")

    async def _execute_with_queue(self, args: BashExecuteArgs, working_dir: str) -> Dict[str, Any]:
        """使用队列执行命令"""
        import threading
        result_event = threading.Event()
        result_data: dict[str, Optional[CommandResult]] = {"result": None}

        def callback_wrapper(command_result: CommandResult):
            """包装回调函数，存储结果并通知主线程"""
            result_data["result"] = command_result
            result_event.set()

        # 将命令加入队列
        command_id = await self.executor.queue_command(
                command=args.command,
                working_directory=working_dir,
                timeout=args.timeout,
                callback=callback_wrapper
            )

        # 等待命令完成（最多等待timeout + 5秒）
        max_wait_time = (args.timeout or 30) + 5
        if result_event.wait(timeout=max_wait_time):
            command_result = result_data["result"]
            if command_result.status == CommandStatus.COMPLETED:
                return self._format_command_result(command_result)
            else:
                return {
                    "status": "failed",
                    "return_code": command_result.return_code,
                    "stdout": command_result.stdout,
                    "stderr": command_result.stderr,
                    "execution_time": command_result.execution_time,
                    "error_message": command_result.error_message or "未知错误"
                }
        else:
            return {
                "status": "timeout",
                "return_code": -1,
                "stdout": "",
                "stderr": "",
                "execution_time": max_wait_time,
                "error_message": f"命令执行超时（等待超过{max_wait_time}秒）"
            }

    def _format_command_result(self, result: CommandResult) -> Dict[str, Any]:
        """格式化命令执行结果"""
        return {
            "status": result.status.value,
            "return_code": result.return_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "execution_time": result.execution_time,
            "error_message": result.error_message
        }

async def execute_bash_command_async(
    command: str,
    working_directory: str = ".",
    timeout: Optional[int] = None,
    use_queue: bool = False,
    callback: Optional[Callable[[CommandResult], None]] = None
) -> str:
    """
    快速执行Bash命令的便捷函数（异步版本）

    Args:
        command: 要执行的命令
        working_directory: 工作目录
        timeout: 超时时间
        use_queue: 是否使用队列
        callback: 执行完成后的回调函数

    Returns:
        命令ID
    """
    executor = get_bash_executor()

    if use_queue:
        return await executor.queue_command(command, working_directory, timeout, callback)
    else:
        return await executor.execute_command(command, working_directory, timeout, callback)