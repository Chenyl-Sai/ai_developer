"""
模型管理器 - 负责延迟模型选择和配置管理
"""
import asyncio
from typing import Optional, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.callbacks.tracers import LoggingCallbackHandler
from ai_dev.core.global_state import GlobalState
from ai_dev.utils.logger import agent_logger


class ModelManager:
    """模型管理器，负责延迟模型选择和配置管理"""

    def __init__(self):
        # 从配置中获取默认模型
        self._cached_models: Dict[str, BaseChatModel] = {}

    def get_model(self, model_name: Optional[str] = None, **kwargs) -> BaseChatModel:
        """
        获取模型实例，延迟创建直到真正需要时

        Args:
            model_name: 模型名称，如果为None则使用默认模型
            **kwargs: 传递给模型构造函数的额外参数

        Returns:
            BaseChatModel: 聊天模型实例
        """
        model_name = model_name or GlobalState.get_config_manager().get_default_model()

        # 检查缓存
        cache_key = f"{model_name}_{str(kwargs)}"
        if cache_key in self._cached_models:
            return self._cached_models[cache_key]

        # 根据配置决定使用哪个模型
        model = self._create_model_instance(model_name, **kwargs)

        # 缓存模型实例
        self._cached_models[cache_key] = model
        return model

    def _create_model_instance(self, model_name: str, **kwargs) -> BaseChatModel:
        """创建模型实例"""
        # 合并默认参数和传入参数
        model_params = self._get_model_params(model_name)
        model_params.update(kwargs)

        # 过滤掉不支持的参数
        supported_params = {k: v for k, v in model_params.items() if k not in ['provider']}

        # 根据模型名称选择不同的聊天模型
        if model_name.startswith("deepseek"):
            return ChatDeepSeek(model=model_name,
                                callbacks=[LoggingCallbackHandler(logger=agent_logger.logger)],
                                **supported_params)
        else:
            return ChatOpenAI(model=model_name, **supported_params)

    def _get_model_params(self, model_name: str) -> Dict[str, Any]:
        """获取模型参数配置"""
        # 从配置管理器中获取模型配置
        model_config = GlobalState.get_config_manager().get_model_config(model_name)
        model_request_config = GlobalState.get_config_manager().get_model_request_config(model_name)

        # 设置API密钥 - 只使用configManager中的配置
        provider = model_config.get("provider", "deepseek" if model_name.startswith("deepseek") else "openai")
        api_key = GlobalState.get_config_manager().get_api_key(provider)

        # 必须从configManager中获取API密钥
        if not api_key:
            raise ValueError(f"未找到 {provider} 的 API 密钥，请通过以下方式配置：\n"
                           f"1. 环境变量: {self._get_env_var_name(provider)}\n"
                           f"2. 配置文件: 在 .ai_dev/config.yaml 中配置 api_keys.{provider}")

        model_request_config["api_key"] = api_key

        return model_request_config

    def _get_env_var_name(self, provider: str) -> str:
        """获取环境变量名称"""
        env_var_mapping = {
            "deepseek": "DEEPSEEK_API_KEY",
            "openai": "OPENAI_API_KEY"
        }
        return env_var_mapping.get(provider, f"{provider.upper()}_API_KEY")

    def _deep_update(self, target: Dict, updates: Dict):
        """深度更新字典"""
        for key, value in updates.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value