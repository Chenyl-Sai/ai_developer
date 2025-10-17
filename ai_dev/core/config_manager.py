"""
配置管理器 - 负责从.ai_dev/config.yaml读取配置
"""

import os
import yaml
import re
from typing import Dict, Any, Optional
from pathlib import Path

from ai_dev.utils.logger import agent_logger


class ConfigManager:
    """配置管理器"""

    def __init__(self, working_directory: str = "."):
        self.working_directory = Path(working_directory).resolve()
        self.config_dir = self.working_directory / ".ai_dev"
        self.config_file = self.config_dir / "config.yaml"
        self._config = None
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self._config is not None:
            return self._config

        # 默认配置
        default_config = {
            "default_model": "deepseek-chat",
            "models": {
                "deepseek-chat": {
                    "provider": "deepseek",
                    "temperature": 0.1,
                    "max_tokens": None,
                    "timeout": 60
                },
                "gpt-4o": {
                    "provider": "openai",
                    "temperature": 0.1,
                    "max_tokens": None,
                    "timeout": 60
                },
                "gpt-4o-mini": {
                    "provider": "openai",
                    "temperature": 0.1,
                    "max_tokens": None,
                    "timeout": 60
                },
                "gpt-3.5-turbo": {
                    "provider": "openai",
                    "temperature": 0.1,
                    "max_tokens": None,
                    "timeout": 60
                }
            },
            "api_keys": {
                "deepseek": "",
                "openai": ""
            },
            "permissions": {
                "allow": [
                    "FileReadTool",
                    "GlobTool",
                    "GrepTool",
                    "TodoWriteTool",
                    "TaskTool"
                ],
                "deny": [
                ],
                "ask": [
                ]
            }
        }

        # 如果配置文件不存在，返回默认配置
        if not self.config_file.exists():
            self._config = default_config
            return self._config

        try:
            # 加载配置文件
            with open(self.config_file, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f) or {}

            # 深度合并用户配置和默认配置
            self._config = self._deep_merge(default_config, user_config)

            # 展开环境变量
            self._config = self._expand_environment_variables(self._config)

            return self._config

        except Exception as e:
            agent_logger.warning(f"警告: 加载配置文件失败，使用默认配置: {e}")
            self._config = default_config
            return self._config

    def _deep_merge(self, base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并两个字典"""
        result = base.copy()

        for key, value in update.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def _expand_environment_variables(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """展开配置中的环境变量"""
        if isinstance(config, dict):
            return {k: self._expand_environment_variables(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._expand_environment_variables(item) for item in config]
        elif isinstance(config, str):
            # 匹配 ${VAR_NAME} 格式的环境变量
            pattern = r'\$\{([^}]+)\}'
            matches = re.findall(pattern, config)

            if matches:
                # 如果有多个环境变量，需要逐个替换
                result = config
                for var_name in matches:
                    env_value = os.getenv(var_name, '')
                    result = result.replace(f'${{{var_name}}}', env_value)
                return result
            else:
                return config
        else:
            return config

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def get_default_model(self) -> str:
        """获取默认模型名称 - 优先从环境变量获取"""
        # 首先尝试从环境变量获取
        env_model = os.getenv("AI_DEV_DEFAULT_MODEL")
        if env_model:
            return env_model

        # 如果环境变量中没有，再从配置文件获取
        return self.get("default_model", "deepseek-chat")

    def get_model_config(self, model_name: str) -> Dict[str, Any]:
        """获取特定模型的配置"""
        return self.get(f"models.{model_name}", {})

    def get_api_key(self, provider: str) -> str:
        """获取API密钥"""
        # 首先尝试从环境变量获取
        env_key = self._get_api_key_from_env(provider)
        if env_key:
            return env_key

        # 如果环境变量中没有，再从配置文件获取
        return self.get(f"api_keys.{provider}", "")

    def _get_api_key_from_env(self, provider: str) -> str:
        """从环境变量获取API密钥"""
        env_var_mapping = {
            "deepseek": "DEEPSEEK_API_KEY",
            "openai": "OPENAI_API_KEY"
        }

        env_var = env_var_mapping.get(provider)
        if env_var:
            return os.getenv(env_var, "")
        return ""