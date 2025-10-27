import copy
from asyncio import QueueEmpty
from typing import Any

from prompt_toolkit.application import get_app
from prompt_toolkit.formatted_text import FormattedText, merge_formatted_text
from prompt_toolkit.layout import Window
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys

from ai_dev.components.common_window import CommonWindow
from ai_dev.components.scrollable_formatted_text_control import ScrollableFormattedTextControl
from ai_dev.core.event_manager import event_manager, Event, EventType
from ai_dev.utils.logger import agent_logger
from ai_dev.utils.render import format_permission_choice

import asyncio

class ChoiceWindow(CommonWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # 记录所有中断
        self.interruptions = asyncio.Queue()
        # 当前任务
        self.current_task = None
        self.current_choice_options: list = []
        self.current_choice_index: int = 0
        # 本轮选择结果，允许多个中断
        self.choice_result = {}
        self.resume_task_ids = set()

        self.choice_control = ScrollableFormattedTextControl(
            self._get_choice_text,
            focusable=True,
            cli = self.cli
        )
        self.window = Window(
            content=self.choice_control,
            always_hide_cursor=True,
        )
        self.choice_kb = KeyBindings()
        self._setup_keybindings()

    async def append_interruption(self, interrupt_info: dict[str, Any]):
        # 都加入队列中
        agent_logger.debug(f"New interruption: {interrupt_info}")
        await self.interruptions.put(interrupt_info)
        # 如果当前没有任务，直接展示
        if self.current_task is None:
            try:
                agent_logger.info(f"Task count befor get {self.interruptions.qsize()}")
                self.current_task = self.interruptions.get_nowait()
                agent_logger.info(f"Task count after get {self.interruptions.qsize()}")
                agent_logger.info(f"Current Task {self.current_task}")
            except:
                pass
        self.cli.re_construct_layout()

    def need_show(self):
        return self.current_task is not None

    def get_choice_key_bindings(self):
        return self.choice_kb

    def _setup_keybindings(self):
        # 选择模式按键绑定
        @self.choice_kb.add('1')
        @self.choice_kb.add('2')
        @self.choice_kb.add('3')
        def handle_choice_key(event):
            key = event.key_sequence[0].key
            asyncio.create_task(self._handle_choice_input(key))

        @self.choice_kb.add(Keys.Up)
        def handle_choice_up(event):
            if self.current_choice_index > 0:
                self.current_choice_index -= 1
                event.app.invalidate()

        @self.choice_kb.add(Keys.Down)
        def handle_choice_down(event):
            if self.current_choice_index < len(self.current_choice_options) - 1:
                self.current_choice_index += 1
                event.app.invalidate()

        @self.choice_kb.add(Keys.Enter)
        def handle_choice_enter(event):
            asyncio.create_task(self._handle_choice_input(str(self.current_choice_index + 1)))

    def _get_choice_text(self):
        choice_content, choice_options = format_permission_choice(self.current_task)
        self.current_choice_options = choice_options
        parts = [choice_content]
        for index, option in enumerate(choice_options):
            if index == self.current_choice_index:
                parts.append(FormattedText([('class:common.blue', "  > " + option + "\n")]))
            else:
                parts.append(FormattedText([("", "    " + option + "\n")]))
        return merge_formatted_text(parts)

    async def _handle_choice_input(self, choice: str):
        """处理选择输入"""
        agent_logger.debug(f"[User select] {choice}, [Queue size]: {self.interruptions.qsize()}")
        if choice not in ['1', '2', '3']:
            await self.cli.output_window.add_common_block("class:error", "❌ 请输入 1、2 或 3")
            return

        # 执行完一个更新个
        self.interruptions.task_done()
        # 记录执行的结果
        self.choice_result[self.current_task.get("_interrupt_id_")] = choice
        self.resume_task_ids.add(self.current_task.get("task_id"))
        self.current_choice_index = 0
        agent_logger.debug(f"choice_result: {self.choice_result}")

        if choice == '3':
            # 当用户选择了取消，立即将队列中剩余的所有中断全部自动标记为拒绝
            while True:
                try:
                    self.current_task = self.interruptions.get_nowait()
                    self.choice_result[self.current_task.get("_interrupt_id_")] = "3"
                    self.resume_task_ids.add(self.current_task.get("task_id"))
                    agent_logger.debug(f"Interrupt [{self.current_task.get('_interrupt_id_')}] auto reject")
                except QueueEmpty:
                    self.current_task = None
                    break
        else:
            # 当用户选择2的时候，遍历后续的中断中，有和当前中断相同类型的自动设置为2
            remaining_tasks = []
            if choice == '2':
                permission_key = self.current_task.get("permission_key")
                while True:
                    try:
                        next_task = self.interruptions.get_nowait()
                        if next_task.get("permission_key") == permission_key:
                            self.choice_result[next_task.get("_interrupt_id_")] = "2"
                            self.resume_task_ids.add(next_task.get("task_id"))
                            agent_logger.debug(f"Interrupt [{next_task.get('_interrupt_id_')}] auto select 2")
                        else:
                            remaining_tasks.append(next_task)
                    except QueueEmpty:
                        break

                if remaining_tasks:
                    for task in remaining_tasks:
                        await self.interruptions.put(task)

            # 还有剩下的继续获取新的中断
            try:
                self.current_task = self.interruptions.get_nowait()
                agent_logger.debug(f"[New Task] {self.current_task}")
                self.refresh()
            except QueueEmpty:
                agent_logger.debug(f"[No Task]")
                self.current_task = None

        # 当所有中断都处理完成之后
        if self.current_task is None:
            # 恢复输入框
            self.cli.re_construct_layout()

            # 处理选择结果
            await self._handle_interruption_recovery(self.choice_result)

    async def _handle_interruption_recovery(self, resume: Any):
        """处理中断恢复"""
        try:
            task_ids = copy.deepcopy(self.resume_task_ids)
            self.resume_task_ids = set()
            self.choice_result = {}
            await self.cli.process_stream_input(resume, list(task_ids))
        except Exception as e:
            await self.cli.output_window.add_common_block("class:error", f"Error: {e}")
            agent_logger.log_agent_error("interruption_recovery", str(e), e, {
                "recovery_input": resume
            })