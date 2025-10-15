"""
Bash 执行器 - 支持异步执行、回调机制和命令队列
"""

import asyncio
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from logging import exception
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path
from queue import Queue, Empty
from dataclasses import dataclass
from enum import Enum

from ai_dev.utils.logger import agent_logger


class CommandStatus(Enum):
    """命令执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CommandResult:
    """命令执行结果"""
    command_id: str
    command: str
    status: CommandStatus
    return_code: int
    stdout: str
    stderr: str
    execution_time: float
    error_message: Optional[str] = None


@dataclass
class CommandTask:
    """命令任务"""
    command_id: str
    command: str
    working_directory: str
    timeout: Optional[int] = None
    callback: Optional[Callable[[CommandResult], None]] = None


class BashExecutor:
    """Bash 执行器 - 支持异步执行和命令队列"""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.command_queue: Queue = Queue()
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.completed_results: Dict[str, CommandResult] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._stop_event = threading.Event()
        self._queue_processor_thread: Optional[threading.Thread] = None

    async def execute_command(
        self,
        command: str,
        working_directory: str = ".",
        timeout: Optional[int] = None,
        callback: Optional[Callable[[CommandResult], None]] = None
    ) -> str:
        """
        异步执行单个命令

        Args:
            command: 要执行的命令
            working_directory: 工作目录
            timeout: 超时时间（秒）
            callback: 执行完成后的回调函数

        Returns:
            命令ID
        """
        command_id = self._generate_command_id()
        task = CommandTask(
            command_id=command_id,
            command=command,
            working_directory=working_directory,
            timeout=timeout,
            callback=callback
        )

        # 直接执行，不加入队列
        asyncio.create_task(self._execute_single_command(task))
        return command_id

    async def queue_command(
        self,
        command: str,
        working_directory: str = ".",
        timeout: Optional[int] = None,
        callback: Optional[Callable[[CommandResult], None]] = None
    ) -> str:
        """
        将命令加入队列等待顺序执行

        Args:
            command: 要执行的命令
            working_directory: 工作目录
            timeout: 超时时间（秒）
            callback: 执行完成后的回调函数

        Returns:
            命令ID
        """
        command_id = self._generate_command_id()
        task = CommandTask(
            command_id=command_id,
            command=command,
            working_directory=working_directory,
            timeout=timeout,
            callback=callback
        )

        self.command_queue.put(task)
        return command_id

    def start_queue_processor(self):
        """启动队列处理器"""
        if self._queue_processor_thread is None or not self._queue_processor_thread.is_alive():
            self._stop_event.clear()
            self._queue_processor_thread = threading.Thread(
                target=self._process_command_queue,
                daemon=True
            )
            self._queue_processor_thread.start()

    def stop_queue_processor(self):
        """停止队列处理器"""
        self._stop_event.set()
        if self._queue_processor_thread:
            self._queue_processor_thread.join(timeout=5)

    async def get_command_result(self, command_id: str) -> Optional[CommandResult]:
        """获取命令执行结果"""
        return self.completed_results.get(command_id)

    def get_all_results(self) -> Dict[str, CommandResult]:
        """获取所有已完成命令的结果"""
        return self.completed_results.copy()

    async def cancel_command(self, command_id: str) -> bool:
        """取消正在执行的命令"""
        if command_id in self.running_tasks:
            task = self.running_tasks[command_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.running_tasks[command_id]
            return True
        return False

    def _generate_command_id(self) -> str:
        """生成唯一的命令ID"""
        import uuid
        return str(uuid.uuid4())

    async def _execute_single_command(self, task: CommandTask):
        """执行单个命令"""
        start_time = asyncio.get_event_loop().time()

        try:
            # 在线程池中执行阻塞的subprocess调用
            result = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._run_command_sync,
                task.command,
                task.working_directory,
                task.timeout
            )

            execution_time = asyncio.get_event_loop().time() - start_time
            command_result = CommandResult(
                command_id=task.command_id,
                command=task.command,
                status=CommandStatus.COMPLETED,
                return_code=result["return_code"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                execution_time=execution_time
            )

        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            command_result = CommandResult(
                command_id=task.command_id,
                command=task.command,
                status=CommandStatus.FAILED,
                return_code=-1,
                stdout="",
                stderr="",
                execution_time=execution_time,
                error_message=str(e)
            )

        # 存储结果
        self.completed_results[task.command_id] = command_result

        # 执行回调
        if task.callback:
            try:
                if asyncio.iscoroutinefunction(task.callback):
                    await task.callback(command_result)
                else:
                    task.callback(command_result)
            except Exception as e:
                agent_logger.info(f"Callback error for command {task.command_id}", exception=e)

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

    def _process_command_queue(self):
        """处理命令队列（在单独的线程中运行）"""
        while not self._stop_event.is_set():
            try:
                # 从队列中获取任务
                task = self.command_queue.get(timeout=1)

                # 直接执行命令（不在事件循环中）
                self._execute_single_command_sync(task)

                self.command_queue.task_done()

            except Empty:
                continue
            except Exception as e:
                agent_logger.error(f"Queue processor error", exception=e)

    def _execute_single_command_sync(self, task: CommandTask):
        """同步执行单个命令（用于队列处理器）"""
        import time
        start_time = time.time()

        try:
            # 执行命令
            result = self._run_command_sync(
                task.command,
                task.working_directory,
                task.timeout
            )

            execution_time = time.time() - start_time
            command_result = CommandResult(
                command_id=task.command_id,
                command=task.command,
                status=CommandStatus.COMPLETED,
                return_code=result["return_code"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                execution_time=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            command_result = CommandResult(
                command_id=task.command_id,
                command=task.command,
                status=CommandStatus.FAILED,
                return_code=-1,
                stdout="",
                stderr="",
                execution_time=execution_time,
                error_message=str(e)
            )

        # 存储结果
        self.completed_results[task.command_id] = command_result

        # 执行回调
        if task.callback:
            try:
                task.callback(command_result)
            except Exception as e:
                agent_logger.error(f"Callback error for command {task.command_id}", exception=e)

    def __del__(self):
        """清理资源"""
        self.stop_queue_processor()
        self.executor.shutdown(wait=False)


# 创建全局执行器实例
_global_executor = BashExecutor()


def get_bash_executor() -> BashExecutor:
    """获取全局Bash执行器"""
    return _global_executor