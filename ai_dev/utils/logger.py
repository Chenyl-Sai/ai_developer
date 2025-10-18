"""
日志工具类 - 提供详细的执行过程跟踪
"""

import os
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from logging.handlers import TimedRotatingFileHandler

from langchain_core.messages import AIMessage

class AgentLogger:
    """Agent执行过程日志记录器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.logger = None
        self.log_file = None
        self.is_initialized = False
        self.log_dir = None

    def initialize(self, working_directory: str = ".", log_level: str = "INFO", log_dir: Optional[str] = None):
        """初始化日志系统"""
        if self.is_initialized:
            return

        # 从环境变量获取配置（优先级：参数 > 环境变量 > 默认值）
        env_log_dir = os.getenv("AI_DEV_LOG_DIR")
        env_log_level = os.getenv("AI_DEV_LOG_LEVEL")

        # 确定日志目录
        if log_dir:
            self.log_dir = Path(log_dir)
        elif env_log_dir:
            self.log_dir = Path(env_log_dir)
        else:
            # 默认日志目录
            self.log_dir = Path("/opt/apps/logs/ai-dev/")

            # 如果默认目录不存在，使用工作目录下的logs目录
            if not self.log_dir.exists():
                self.log_dir = Path(working_directory) / ".ai_dev/logs"

        # 确定日志级别
        final_log_level = log_level
        if env_log_level:
            final_log_level = env_log_level

        # 创建日志目录
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 生成日志文件名（按天滚动）
        log_filename = "ai_agent.log"
        self.log_file = self.log_dir / log_filename

        # 配置日志记录器
        self.logger = logging.getLogger("ai_agent")
        self.logger.setLevel(getattr(logging, final_log_level.upper()))

        # 避免重复添加处理器
        if not self.logger.handlers:
            # 按天滚动的文件处理器
            file_handler = TimedRotatingFileHandler(
                self.log_file,
                when="midnight",  # 每天午夜滚动
                interval=1,       # 每天
                backupCount=7,    # 保留7天的日志
                encoding='utf-8'
            )
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

            # 控制台处理器 - 在prompt_toolkit环境中禁用，防止干扰用户界面
            # 只有在非交互式环境中才启用控制台输出
            if not self._is_prompt_toolkit_environment():
                console_handler = logging.StreamHandler(sys.stdout)
                console_formatter = logging.Formatter(
                    '%(asctime)s - %(levelname)s - %(message)s'
                )
                console_handler.setFormatter(console_formatter)
                console_handler.setLevel(logging.WARNING)  # 控制台只显示警告和错误
                self.logger.addHandler(console_handler)

        self.is_initialized = True
        self.logger.info(f"日志系统初始化完成，日志目录: {self.log_dir}, 日志文件: {self.log_file}")

    def log_agent_start(self, agent_id: str, user_input: str):
        """记录Agent开始执行"""
        if self.logger:
            self.logger.info(f"[AGENT_START] Agent: {agent_id}, 输入: {user_input}")

    def log_agent_complete(self, agent_id: str, response: str):
        """记录Agent执行完成"""
        if self.logger:
            self.logger.info(f"[AGENT_COMPLETE] Agent: {agent_id}, 响应长度: {len(response)}")

    def log_agent_error(self, agent_id: str, error: str, exception: Exception = None, context: dict = None):
        """记录Agent执行错误"""
        if self.logger:
            import traceback
            stack_trace = traceback.format_exc()
            if stack_trace.strip() == "None":
                # 如果没有异常堆栈，获取当前调用堆栈
                stack_trace = ''.join(traceback.format_stack()[:-1])

            # 构建详细的错误信息
            error_details = f"[AGENT_ERROR] Agent: {agent_id}, 错误: {error}"

            # 添加上下文信息
            if context:
                context_str = ", ".join([f"{k}: {v}" for k, v in context.items()])
                error_details += f", 上下文: {context_str}"

            # 添加异常类型信息
            if exception:
                error_details += f", 异常类型: {type(exception).__name__}"

            error_details += f"\n堆栈信息:\n{stack_trace}"

            self.logger.error(error_details)

    def log_reasoning_start(self, agent_id: str, iteration: int):
        """记录推理开始"""
        if self.logger:
            self.logger.info(f"[REASONING_START] Agent: {agent_id}, 迭代: {iteration}")

    def log_reasoning_complete(self, agent_id: str, iteration: int, response: str, tool_calls: list):
        """记录推理完成"""
        if self.logger:
            tool_info = f", 工具调用: {len(tool_calls)}个" if tool_calls else ""
            self.logger.info(f"[REASONING_COMPLETE] Agent: {agent_id}, 迭代: {iteration}, 响应长度: {len(response)}{tool_info}")

    def log_tool_call(self, agent_id: str, tool_name: str, tool_args: dict):
        """记录工具调用"""
        if self.logger:
            self.logger.info(f"[TOOL_CALL] Agent: {agent_id}, 工具: {tool_name}, 参数: {tool_args}")

    def log_tool_result(self, agent_id: str, tool_name: str, result: str, success: bool):
        """记录工具执行结果"""
        if self.logger:
            status = "成功" if success else "失败"
            result_preview = str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
            self.logger.info(f"[TOOL_RESULT] Agent: {agent_id}, 工具: {tool_name}, 状态: {status}, 结果预览: {result_preview}")

            # 记录完整的结果（调试级别）
            if success and result:
                sanitized_result = self._sanitize_content(str(result))
                self.logger.debug(f"[TOOL_RESULT_DETAIL] Agent: {agent_id}, 工具: {tool_name}, 完整结果: {sanitized_result}")

    def log_model_call(self, agent_id: str, model_name: str, input_length: int, conversation_history: list = None):
        """记录模型调用"""
        if self.logger:
            self.logger.info(f"[MODEL_CALL] Agent: {agent_id}, 模型: {model_name}, 输入长度: {input_length}")

            # 记录详细的对话历史
            if conversation_history:
                for i, msg in enumerate(conversation_history):
                    msg_type = type(msg).__name__
                    content = self._sanitize_content(msg.content) if hasattr(msg, 'content') else str(msg)
                    self.logger.debug(f"[MODEL_INPUT_{i}] Agent: {agent_id}, 类型: {msg_type}, 内容: {content}")

    def log_model_response(self, agent_id: str, model_name: str, ai_message: AIMessage = None):
        """记录模型响应"""
        if self.logger:
            self.logger.info(f"[MODEL_RESPONSE] Agent: {agent_id}, 模型: {model_name}")

            # 记录详细的响应内容
            self.logger.debug(f"[MODEL_OUTPUT] 完整响应: {ai_message}")

    def log_state_update(self, agent_id: str, state_changes: dict):
        """记录状态更新"""
        if self.logger:
            changes_str = ", ".join([f"{k}: {v}" for k, v in state_changes.items()])
            self.logger.debug(f"[STATE_UPDATE] Agent: {agent_id}, 变更: {changes_str}")

    def log_stream_chunk(self, agent_id: str, chunk_type: str, content_length: int):
        """记录流式输出块"""
        if self.logger:
            self.logger.debug(f"[STREAM_CHUNK] Agent: {agent_id}, 类型: {chunk_type}, 长度: {content_length}")

    def log_no_response(self, agent_id: str, reason: str = "未知原因"):
        """记录没有生成响应的情况"""
        if self.logger:
            self.logger.warning(f"[NO_RESPONSE] Agent: {agent_id}, 原因: {reason}")

    def get_log_file_path(self) -> Optional[Path]:
        """获取日志文件路径"""
        return self.log_file

    def get_log_dir(self) -> Optional[Path]:
        """获取日志目录"""
        return self.log_dir

    def debug(self, message: str):
        """调试级别日志"""
        if self.logger:
            self.logger.debug(message)

    def info(self, message: str):
        """信息级别日志"""
        if self.logger:
            self.logger.info(message)

    def warning(self, message: str):
        """警告级别日志"""
        if self.logger:
            self.logger.warning(message)

    def error(self, message: str, exception: Exception = None, context: dict = None):
        """错误级别日志"""
        if self.logger:
            import traceback
            stack_trace = traceback.format_exc()
            if stack_trace.strip() == "None":
                # 如果没有异常堆栈，获取当前调用堆栈
                stack_trace = ''.join(traceback.format_stack()[:-1])

            # 构建详细的错误信息
            error_details = message

            # 添加上下文信息
            if context:
                context_str = ", ".join([f"{k}: {v}" for k, v in context.items()])
                error_details += f", 上下文: {context_str}"

            # 添加异常类型信息
            if exception:
                error_details += f", 异常类型: {type(exception).__name__}"

            error_details += f"\n堆栈信息:\n{stack_trace}"

            self.logger.error(error_details)



    def _is_prompt_toolkit_environment(self) -> bool:
        """
        检测是否在prompt_toolkit环境中运行

        Returns:
            如果是prompt_toolkit环境返回True，否则返回False
        """
        # 检查是否导入了prompt_toolkit模块
        try:
            import prompt_toolkit
            # 检查是否有活动的prompt_toolkit应用
            from prompt_toolkit.application import get_app
            try:
                app = get_app()
                return app is not None
            except:
                # 如果没有活动的应用，检查是否在交互式环境中
                return 'prompt_toolkit' in sys.modules
        except ImportError:
            # 没有安装prompt_toolkit
            return False

    def _sanitize_content(self, content: str) -> str:
        """
        过滤敏感信息，防止API密钥等敏感数据被记录到日志中

        Args:
            content: 原始内容

        Returns:
            过滤后的安全内容
        """
        if not content:
            return content

        sanitized = content

        # 过滤常见的API密钥模式
        import re

        # OpenAI API密钥模式 (sk-...)
        sanitized = re.sub(r'sk-[a-zA-Z0-9]{20,}', 'sk-***REDACTED***', sanitized)

        # DeepSeek API密钥模式
        sanitized = re.sub(r'[a-f0-9]{32}', '***REDACTED***', sanitized)

        # 通用API密钥模式（32位以上字母数字）
        sanitized = re.sub(r'[a-zA-Z0-9]{32,}', '***REDACTED***', sanitized)

        # 过滤可能的密码字段
        password_patterns = [
            r'"password"\s*:\s*"[^"]+"',
            r'"api_key"\s*:\s*"[^"]+"',
            r'"secret"\s*:\s*"[^"]+"',
            r'"token"\s*:\s*"[^"]+"'
        ]

        for pattern in password_patterns:
            sanitized = re.sub(pattern, lambda m: m.group(0).split('"')[-2] + '"***REDACTED***"', sanitized)

        return sanitized


# 全局日志实例
agent_logger = AgentLogger()