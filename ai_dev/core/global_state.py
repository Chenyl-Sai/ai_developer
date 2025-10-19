"""
全局状态管理器 - 提供全局可静态访问的数据存储
"""

import os
from typing import Dict, Any, Optional
from pathlib import Path

from ..models.state import EnvironmentState
from ai_dev.utils.collection import AsyncBatchQueue


class GlobalState:
    """
    全局状态管理器 - 单例模式实现
    提供全局可静态访问的数据存储
    """

    _instance = None
    _environment_state: Optional[EnvironmentState] = None
    _config_manager = None
    _model_manager = None
    _cli_instance = None
    _user_input_queue: AsyncBatchQueue = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def initialize(cls, working_directory: str = ".") -> 'GlobalState':
        """初始化全局状态"""
        instance = cls()
        instance._environment_state = EnvironmentState(
            working_directory=working_directory,
            files=[],
            git_info=None,
            system_info={}
        )
        cls._user_input_queue = AsyncBatchQueue()
        return instance

    @classmethod
    def get_working_directory(cls) -> str:
        """获取工作目录"""
        if cls._environment_state:
            return cls._environment_state.working_directory
        return os.getcwd()

    @classmethod
    def set_working_directory(cls, path: str):
        """设置工作目录"""
        if cls._environment_state:
            cls._environment_state.working_directory = path

    @classmethod
    def get_environment_info(cls) -> Dict[str, Any]:
        """获取环境信息"""
        if cls._environment_state:
            return {
                'working_directory': cls._environment_state.working_directory,
                'files': cls._environment_state.files,
                'git_info': cls._environment_state.git_info,
                'system_info': cls._environment_state.system_info
            }
        return {}

    @classmethod
    def update_system_info(cls, info: Dict[str, Any]):
        """更新系统信息"""
        if cls._environment_state:
            cls._environment_state.system_info.update(info)

    @classmethod
    def set_config_manager(cls, config_manager):
        """设置配置管理器实例"""
        cls._config_manager = config_manager

    @classmethod
    def get_config_manager(cls):
        """获取配置管理器实例"""
        return cls._config_manager

    @classmethod
    def set_model_manager(cls, model_manager):
        cls._model_manager = model_manager

    @classmethod
    def get_model_manager(cls):
        return cls._model_manager

    @classmethod
    def set_cli_instance(cls, cli_instance):
        """设置CLI实例"""
        cls._cli_instance = cli_instance

    @classmethod
    def get_cli_instance(cls):
        """获取CLI实例"""
        return cls._cli_instance

    @classmethod
    def get_absolute_path(cls, relative_path: str) -> str:
        """获取相对于工作目录的绝对路径"""
        working_dir = cls.get_working_directory()
        return str(Path(working_dir) / relative_path)

    @classmethod
    def is_initialized(cls) -> bool:
        """检查是否已初始化"""
        return cls._environment_state is not None

    @classmethod
    def get_user_input_queue(cls) -> AsyncBatchQueue:
        return cls._user_input_queue