"""
Bash 执行工具 - 支持异步执行、回调机制和命令队列
"""

import asyncio
import subprocess
from typing import Any, Dict, Optional, Callable, Type, Generator, AsyncGenerator
from pydantic import BaseModel, Field
from ai_dev.tools.base import StreamTool, CommonToolArgs
from ai_dev.utils.bash_executor import (
    BashExecutor,
    CommandResult,
    CommandStatus,
    get_bash_executor
)
from ai_dev.core.global_state import GlobalState
from .prompt_cn import prompt

class BashExecuteArgs(CommonToolArgs):
    """Bash 执行工具参数"""
    command: str = Field(..., description="The command to execute")
    propose: str = Field(description="Briefly explain the intention of the bash script executed this time")
    timeout: Optional[int] = Field(default=None, description="Optional timeout in seconds (max 600)")

class BashExecuteTool(StreamTool):
    """Bash 执行工具"""

    name: str = "BashExecuteTool"
    description: str = prompt
    args_schema: Type[BaseModel] = BashExecuteArgs

    # 全局执行器实例
    _executor: Optional[BashExecutor] = None

    @property
    def show_name(self) -> str:
        return "Bash"

    @property
    def executor(self) -> BashExecutor:
        """获取执行器实例"""
        if self._executor is None:
            self._executor = BashExecutor()
            self._executor.start_queue_processor()
        return self._executor

    async def _execute_tool(self, **kwargs) -> AsyncGenerator[dict, None]:
        """执行工具逻辑 - 同步等待命令完成并返回结果"""
        args = BashExecuteArgs(**kwargs)

        # 验证工作目录
        working_dir = GlobalState.get_working_directory()

        # 都直接执行
        use_queue = False
        if use_queue:
            # 对于队列执行，使用队列处理器
            result_data = self._execute_with_queue(args, working_dir)
        else:
            # 对于直接执行，直接运行命令
            result_data = self._execute_direct(args, working_dir)

        yield {
            "type": "tool_end",
            "source": kwargs.get("context").get("agent_id"),
            "result_for_llm": result_data,
            "context": kwargs.get("context")
        }

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
    def _format_args(self, kwargs: Dict[str, Any]) -> str:
        command = kwargs.get("command")
        MAX_SHOW_LINES = 3
        MAX_CHARS_PER_LINE = 200
        if not command:
            return ""

        # 按换行符分割字符串
        lines = command.split('\n')
        truncated_lines = lines[:MAX_SHOW_LINES]

        # 对每一行进行字符数截取
        result_lines = []
        for line in truncated_lines:
            # 如果行长度超过限制，则截取并在末尾添加省略号
            if len(line) > MAX_CHARS_PER_LINE:
                truncated_line = line[:MAX_CHARS_PER_LINE] + "..."
            else:
                truncated_line = line
            result_lines.append(truncated_line)

        # 如果原始行数超过最大行数，在最后添加省略号表示还有更多内容
        if len(lines) > MAX_SHOW_LINES:
            result_lines.append("...")

        # 用换行符连接所有行
        return '\n'.join(result_lines)


    def _get_success_message(self, result_for_show: Any) -> str:
        """生成成功消息"""
        # 优先检查 stderr 和 error_message
        return ""

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