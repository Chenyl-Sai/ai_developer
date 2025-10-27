"""
全局事件管理器
支持发布-订阅模式的事件系统，用于处理全局中断事件
"""
import asyncio
from typing import Dict, List, Callable, Any, Optional
from enum import Enum
from dataclasses import dataclass
from ..utils.logger import agent_logger


class EventType(Enum):
    """事件类型枚举"""
    USER_CANCEL = "user_cancel"  # 全局中断事件
    REFUSE_AUTH = "refuse_auth"  # 拒绝授权事件


@dataclass
class Event:
    """事件数据类"""
    event_type: EventType
    data: Dict[str, Any]
    source: Optional[str] = None
    timestamp: Optional[float] = None


class EventManager:
    """全局事件管理器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._subscribers: Dict[EventType, List[Callable]] = {}
            self._event_queue: asyncio.Queue = asyncio.Queue()
            self._processing_task: Optional[asyncio.Task] = None
            self._is_running = False
            self._initialized = True

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """订阅事件

        Args:
            event_type: 事件类型
            callback: 回调函数，接收Event参数
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        if callback not in self._subscribers[event_type]:
            self._subscribers[event_type].append(callback)
            agent_logger.debug(f"订阅事件: {event_type.value}, 当前订阅者数: {len(self._subscribers[event_type])}")

    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """取消订阅事件

        Args:
            event_type: 事件类型
            callback: 要移除的回调函数
        """
        if event_type in self._subscribers and callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
            agent_logger.debug(f"取消订阅事件: {event_type.value}, 剩余订阅者数: {len(self._subscribers[event_type])}")

    async def publish(self, event: Event) -> None:
        """发布事件

        Args:
            event: 事件对象
        """
        if not self._is_running:
            agent_logger.warning("事件管理器未启动，事件将被丢弃")
            return

        await self._event_queue.put(event)
        agent_logger.debug(f"发布事件: {event.event_type.value}, 队列大小: {self._event_queue.qsize()}")

    async def _process_events(self) -> None:
        """事件处理循环"""
        while self._is_running:
            try:
                event = await self._event_queue.get()
                await self._dispatch_event(event)
                self._event_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                agent_logger.error(f"处理事件时出错: {e}", exception=e)

    async def _dispatch_event(self, event: Event) -> None:
        """分发事件给所有订阅者

        Args:
            event: 事件对象
        """
        event_type = event.event_type

        if event_type not in self._subscribers:
            return

        subscribers = self._subscribers[event_type].copy()

        # 分离同步和异步回调
        sync_callbacks = []
        async_callbacks = []

        for callback in subscribers:
            if asyncio.iscoroutinefunction(callback):
                async_callbacks.append(callback)
            else:
                sync_callbacks.append(callback)

        # 先执行所有同步回调
        for callback in sync_callbacks:
            try:
                callback(event)
            except Exception as e:
                agent_logger.error(f"同步事件处理回调执行失败: {e}", exception=e)

        # 并发执行所有异步回调
        if async_callbacks:
            tasks = []
            for callback in async_callbacks:
                tasks.append(callback(event))

            if tasks:
                try:
                    await asyncio.gather(*tasks, return_exceptions=True)
                except Exception as e:
                    agent_logger.error(f"异步事件处理回调执行失败: {e}", exception=e)

    async def start(self) -> None:
        """启动事件管理器"""
        if self._is_running:
            return

        self._is_running = True
        self._processing_task = asyncio.create_task(self._process_events())
        agent_logger.info("事件管理器已启动")

    async def stop(self) -> None:
        """停止事件管理器"""
        if not self._is_running:
            return

        self._is_running = False

        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

        # 清空事件队列
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
                self._event_queue.task_done()
            except asyncio.QueueEmpty:
                break

        agent_logger.info("事件管理器已停止")

    def get_subscriber_count(self, event_type: EventType) -> int:
        """获取指定事件的订阅者数量

        Args:
            event_type: 事件类型

        Returns:
            订阅者数量
        """
        return len(self._subscribers.get(event_type, []))

    def is_running(self) -> bool:
        """检查事件管理器是否正在运行

        Returns:
            是否正在运行
        """
        return self._is_running


# 全局事件管理器实例
event_manager = EventManager()