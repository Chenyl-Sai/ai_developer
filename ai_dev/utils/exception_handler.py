"""
异常处理工具类 - 提供统一的异常处理和日志记录
"""

import traceback
from typing import Optional, Dict, Any
from .logger import agent_logger


class ExceptionHandler:
    """异常处理器"""

    @staticmethod
    def handle_exception(
        exception: Exception,
        context: str,
        user_message: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        统一处理异常

        Args:
            exception: 异常对象
            context: 异常发生的上下文描述
            user_message: 给用户的友好错误消息（可选）
            additional_context: 额外的上下文信息（可选）

        Returns:
            给用户的错误消息
        """
        # 获取异常详细信息
        error_type = type(exception).__name__
        error_message = str(exception)

        # 构建上下文信息
        context_info = {
            "context": context,
            "error_type": error_type,
            "error_message": error_message
        }

        # 添加额外的上下文信息
        if additional_context:
            context_info.update(additional_context)

        # 记录详细的错误日志
        agent_logger.error(
            f"处理异常: {context}",
            exception=exception,
            context=context_info
        )

        # 返回给用户的错误消息
        if user_message:
            return user_message
        else:
            return f"{context}时发生错误: {error_message}"

    @staticmethod
    def safe_execute(
        func,
        context: str,
        default_return=None,
        user_message: Optional[str] = None,
        **kwargs
    ):
        """
        安全执行函数，捕获异常并记录日志

        Args:
            func: 要执行的函数
            context: 执行上下文描述
            default_return: 异常时的默认返回值
            user_message: 给用户的友好错误消息（可选）
            **kwargs: 函数参数

        Returns:
            函数执行结果或默认返回值
        """
        try:
            return func(**kwargs)
        except Exception as e:
            ExceptionHandler.handle_exception(e, context, user_message, kwargs)
            return default_return

    @staticmethod
    async def safe_execute_async(
        func,
        context: str,
        default_return=None,
        user_message: Optional[str] = None,
        **kwargs
    ):
        """
        安全执行异步函数，捕获异常并记录日志

        Args:
            func: 要执行的异步函数
            context: 执行上下文描述
            default_return: 异常时的默认返回值
            user_message: 给用户的友好错误消息（可选）
            **kwargs: 函数参数

        Returns:
            函数执行结果或默认返回值
        """
        try:
            return await func(**kwargs)
        except Exception as e:
            ExceptionHandler.handle_exception(e, context, user_message, kwargs)
            return default_return

    @staticmethod
    def get_exception_details(exception: Exception) -> Dict[str, Any]:
        """
        获取异常的详细信息

        Args:
            exception: 异常对象

        Returns:
            包含异常详细信息的字典
        """
        return {
            "type": type(exception).__name__,
            "message": str(exception),
            "traceback": traceback.format_exc(),
            "module": exception.__class__.__module__,
            "file": getattr(exception, '__traceback__', None)
        }

    @staticmethod
    def classify_exception(exception: Exception) -> str:
        """
        对异常进行分类

        Args:
            exception: 异常对象

        Returns:
            异常分类
        """
        error_type = type(exception).__name__

        # 网络相关异常
        network_errors = ["ConnectionError", "TimeoutError", "HTTPError", "RequestException"]
        if error_type in network_errors:
            return "network_error"

        # 文件系统相关异常
        file_errors = ["FileNotFoundError", "PermissionError", "IOError", "OSError"]
        if error_type in file_errors:
            return "file_system_error"

        # 配置相关异常
        config_errors = ["KeyError", "ValueError", "TypeError", "AttributeError"]
        if error_type in config_errors:
            return "configuration_error"

        # 内存相关异常
        memory_errors = ["MemoryError"]
        if error_type in memory_errors:
            return "memory_error"

        # 其他异常
        return "general_error"