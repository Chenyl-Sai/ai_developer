"""
错误恢复机制 - 提供异常后的恢复策略
"""

import asyncio
import time
from typing import Optional, Callable, Any
from .logger import agent_logger
from .exception_handler import ExceptionHandler


class ErrorRecovery:
    """错误恢复管理器"""

    @staticmethod
    def retry_with_backoff(
        func: Callable,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        retry_on_exceptions: tuple = None,
        context: str = "执行操作"
    ) -> Any:
        """
        使用指数退避策略重试函数

        Args:
            func: 要重试的函数
            max_retries: 最大重试次数
            initial_delay: 初始延迟时间（秒）
            max_delay: 最大延迟时间（秒）
            backoff_factor: 退避因子
            retry_on_exceptions: 需要重试的异常类型
            context: 操作上下文描述

        Returns:
            函数执行结果

        Raises:
            最后一次尝试的异常
        """
        if retry_on_exceptions is None:
            retry_on_exceptions = (Exception,)

        last_exception = None
        delay = initial_delay

        for attempt in range(max_retries + 1):
            try:
                return func()
            except retry_on_exceptions as e:
                last_exception = e

                # 如果是最后一次尝试，不再等待
                if attempt == max_retries:
                    break

                # 记录重试信息
                agent_logger.warning(
                    f"{context}失败，第 {attempt + 1}/{max_retries} 次重试，等待 {delay:.1f} 秒: {str(e)}"
                )

                # 等待
                time.sleep(delay)

                # 更新延迟时间
                delay = min(delay * backoff_factor, max_delay)

        # 所有重试都失败
        raise last_exception

    @staticmethod
    async def retry_with_backoff_async(
        func: Callable,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        retry_on_exceptions: tuple = None,
        context: str = "执行异步操作"
    ) -> Any:
        """
        使用指数退避策略重试异步函数

        Args:
            func: 要重试的异步函数
            max_retries: 最大重试次数
            initial_delay: 初始延迟时间（秒）
            max_delay: 最大延迟时间（秒）
            backoff_factor: 退避因子
            retry_on_exceptions: 需要重试的异常类型
            context: 操作上下文描述

        Returns:
            函数执行结果

        Raises:
            最后一次尝试的异常
        """
        if retry_on_exceptions is None:
            retry_on_exceptions = (Exception,)

        last_exception = None
        delay = initial_delay

        for attempt in range(max_retries + 1):
            try:
                return await func()
            except retry_on_exceptions as e:
                last_exception = e

                # 如果是最后一次尝试，不再等待
                if attempt == max_retries:
                    break

                # 记录重试信息
                agent_logger.warning(
                    f"{context}失败，第 {attempt + 1}/{max_retries} 次重试，等待 {delay:.1f} 秒: {str(e)}"
                )

                # 等待
                await asyncio.sleep(delay)

                # 更新延迟时间
                delay = min(delay * backoff_factor, max_delay)

        # 所有重试都失败
        raise last_exception

    @staticmethod
    def fallback_strategy(
        primary_func: Callable,
        fallback_func: Callable,
        fallback_condition: Optional[Callable[[Exception], bool]] = None,
        context: str = "执行操作"
    ) -> Any:
        """
        使用备用策略执行操作

        Args:
            primary_func: 主要函数
            fallback_func: 备用函数
            fallback_condition: 触发备用策略的条件（可选）
            context: 操作上下文描述

        Returns:
            主要函数或备用函数的执行结果
        """
        try:
            return primary_func()
        except Exception as e:
            # 检查是否应该使用备用策略
            if fallback_condition and not fallback_condition(e):
                raise e

            # 记录备用策略使用
            agent_logger.warning(
                f"{context}主要策略失败，使用备用策略: {str(e)}"
            )

            try:
                return fallback_func()
            except Exception as fallback_error:
                # 备用策略也失败
                agent_logger.error(
                    f"{context}备用策略也失败",
                    exception=fallback_error
                )
                raise fallback_error

    @staticmethod
    async def fallback_strategy_async(
        primary_func: Callable,
        fallback_func: Callable,
        fallback_condition: Optional[Callable[[Exception], bool]] = None,
        context: str = "执行异步操作"
    ) -> Any:
        """
        使用备用策略执行异步操作

        Args:
            primary_func: 主要异步函数
            fallback_func: 备用异步函数
            fallback_condition: 触发备用策略的条件（可选）
            context: 操作上下文描述

        Returns:
            主要函数或备用函数的执行结果
        """
        try:
            return await primary_func()
        except Exception as e:
            # 检查是否应该使用备用策略
            if fallback_condition and not fallback_condition(e):
                raise e

            # 记录备用策略使用
            agent_logger.warning(
                f"{context}主要策略失败，使用备用策略: {str(e)}"
            )

            try:
                return await fallback_func()
            except Exception as fallback_error:
                # 备用策略也失败
                agent_logger.error(
                    f"{context}备用策略也失败",
                    exception=fallback_error
                )
                raise fallback_error

    @staticmethod
    def is_recoverable_error(exception: Exception) -> bool:
        """
        判断错误是否可恢复

        Args:
            exception: 异常对象

        Returns:
            是否可恢复
        """
        error_type = type(exception).__name__

        # 可恢复的错误类型
        recoverable_errors = [
            "ConnectionError",
            "TimeoutError",
            "TemporaryError",
            "RateLimitError"
        ]

        # 不可恢复的错误类型
        unrecoverable_errors = [
            "MemoryError",
            "SyntaxError",
            "KeyboardInterrupt",
            "SystemExit"
        ]

        if error_type in unrecoverable_errors:
            return False

        if error_type in recoverable_errors:
            return True

        # 默认情况下，大多数错误被认为是可恢复的
        return True