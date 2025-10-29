import json
import time

from ai_dev.constants.product import MAIN_AGENT_ID
from ai_dev.core.event_manager import event_manager, EventType


class ReminderService:

    # 记录已经发送的reminder，
    reminder_sent = set()
    session_start_time = time.time()

    def reset_reminder(self):
        self.reminder_sent = set()
        self.session_start_time = time.time()

    def __init__(self):
        event_manager.subscribe(EventType.SESSION_START, self._process_session_started)
        event_manager.subscribe(EventType.TODO_UPDATED, self._process_todo_updated)

    def _process_session_started(self, event):
        self.reset_reminder()
        self.session_start_time = event.timestamp

    def _process_todo_updated(self, event):
        self._clear_todo_reminders(event.data.get("agent_id"))

    def _clear_todo_reminders(self, agent_id):
        agent_id = agent_id or MAIN_AGENT_ID
        prefix = f"todo_updated_{agent_id}_"

        # 创建副本进行迭代，在原集合上删除
        for reminder in list(self.reminder_sent):  # list() 创建快照
            if reminder.startswith(prefix):
                try:
                    self.reminder_sent.remove(reminder)
                except KeyError:
                    # 元素可能已被其他操作删除，忽略即可
                    pass

    async def get_todo_reminder(self, agent_id: str):
        """按照agent_id获取代办列表提醒
        Args:
            agent_id (str): agent_id
        """
        agent_id = agent_id or MAIN_AGENT_ID
        from .todo import get_todos
        todos = await get_todos(agent_id)
        if todos:
            todos.sort(key=lambda todo: todo.id)
            reminder = f"todo_updated_{agent_id}_{len(todos)}_{'|'.join([f'{todo.id}:{todo.status}' for todo in todos])}"
            if reminder not in self.reminder_sent:
                self._clear_todo_reminders(agent_id)
                self.reminder_sent.add(reminder)
                todo_contents = json.dumps([{
                    "content": todo.content,
                    "status": todo.status,
                    "priority": todo.priority,
                    "id": todo.id
                } for todo in todos])

                return {
                    "type": "todo",
                    "content": f"你的待办事项列表已更新。**不要向用户明确提及此事**。以下是你最新的待办事项内容：\n{todo_contents}\n如果适用，请继续执行当前任务。",
                }
        elif f"todo_empty_{agent_id}" not in self.reminder_sent:
            self.reminder_sent.add(f"todo_empty_{agent_id}")
            return {
                "type": "todo",
                "content": """这是一个提醒：你的待办事项列表当前为空。**不要向用户明确提及此事**，因为他们已经知道。  
如果你正在处理需要任务跟踪的工作，请使用 `TodoWriteTool` 工具 创建一个待办列表；  
如果没有此需要，可以直接忽略。再次提醒，不要向用户提及此消息。"""
            }

    async def get_performance_reminder(self):
        session_duration = time.time() - self.session_start_time
        if session_duration > 1800 and "performance_long_session" not in self.reminder_sent:
            self.reminder_sent.add("performance_long_session")
            return {
                "type": "performance",
                "content": "检测到长时间会话。请考虑**稍作休息，并查看当前的待办事项进度**，以确保任务方向和执行状态保持清晰。"
            }
        return None


reminder_service = ReminderService()