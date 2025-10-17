import asyncio

from ai_dev.components.scrollable_formatted_text_control import ScrollableFormattedTextControl
from prompt_toolkit.formatted_text import HTML, FormattedText, merge_formatted_text
from prompt_toolkit.layout import Window

from ai_dev.core.global_state import GlobalState
from ai_dev.utils.render import format_ai_output, format_patch_output, format_base_execute_tool_output, format_todo_list
from ai_dev.components.common_window import CommonWindow
from ai_dev.utils.todo import TodoItemStorage
from ai_dev.utils.logger import agent_logger
from ai_dev.core.event_manager import event_manager, EventType, Event


class OutputWindow(CommonWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output_lines: list[tuple[str, str]] = []  # (kind, text)
        self.todo_lines: list[TodoItemStorage] = []
        # 输出控制
        self.output_control = ScrollableFormattedTextControl(
            self._get_full_output_text,
            focusable=True,
        )
        self.window = Window(
            content=self.output_control,
            wrap_lines=True,
            always_hide_cursor=True,
        )
        self.output_lock = asyncio.Lock()
        self.output_cache = []
        self._refresh_output_cache_running = False
        self._compensation_pending_input_running = False
        event_manager.subscribe(EventType.INTERRUPT, self._process_user_interrupt)

    def set_auto_scroll(self, auto_scroll: bool):
        self.output_control.auto_scroll = auto_scroll

    async def add_output(self, kind: str, text: str, append: bool = False):
        """添加输出行"""
        async with self.output_lock:
            if append and self.output_lines and self.output_lines[-1][0] == kind:
                self.output_lines[-1] = (kind, self.output_lines[-1][1] + text)
            else:
                self.output_lines.append((kind, text))
        self.refresh()

    async def add_outputs(self, kind: str, texts: list[str]):
        """添加多个输出行"""
        for text in texts:
            await self.add_output(kind, text)

    async def remove_user_input(self, text: str):
        # 查找最近的这条用户输入删除掉
        async with self.output_lock:
            for i in range(len(self.output_lines) - 1, -1, -1):  # 倒序遍历索引
                if self.output_lines[i][0] == 'output_user' and self.output_lines[i][1] == text:
                    del self.output_lines[i]
                    break
        self.refresh()

    async def user_pending_input_consumed(self, user_inputs: list[str]):
        for index, user_input in enumerate(user_inputs):
            if index == 0:
                await self.add_output("output_user", f"\n> {user_input}\n")
            else:
                await self.add_output("output_user", f"  {user_input}\n")

    def set_todo_lines(self, todos: list):
        """设置待办列表"""
        self.todo_lines = todos
        self.refresh()

    def _get_full_output_text(self):
        # 同步函数，只读缓存
        return self.output_cache[0] if self.output_cache else ""

    async def refresh_output_cache(self):
        tasks = [self._get_output_part(),
                 self._get_user_input_pending_part(),
                 self._get_todo_part()]
        parts = await asyncio.gather(*tasks)
        async with self.output_lock:
            self.output_cache = [merge_formatted_text(sum(parts, []))]

    async def refresh_output_cache_loop(self):
        """定时刷新需要展示的内容缓存"""
        self._refresh_output_cache_running = True
        try:
            while self._refresh_output_cache_running:
                await self.refresh_output_cache()
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            self._refresh_output_cache_running = False

    async def compensation_pending_input_loop(self):
        """异步任务，定时补偿那些输入的时候判断图正在运行导致输入Pending了，但是图又运行完了，导致一致Pending的问题"""
        self._compensation_pending_input_running = True
        try:
            while self._compensation_pending_input_running:
                # 先判断一下当前图的状态
                config = {
                    "configurable": {
                        "thread_id": self.cli.thread_id,
                    }
                }
                if await self.cli.assistant.get_agent_state(config) == "Finished":
                    # 当前是否有Pending信息
                    pending_inputs = await GlobalState.get_user_input_queue().pop_all()
                    if pending_inputs:
                        agent_logger.info("[compensation_pending_input_loop] effective!")
                        await self.user_pending_input_consumed(pending_inputs)
                        await self.cli.process_stream_input("\n".join(pending_inputs))
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        finally:
            self._compensation_pending_input_running = False


    async def _get_output_part(self):
        output_parts = []
        for kind, text in self.output_lines:
            if kind == "output_user":
                output_parts.append(FormattedText([('class:user', text + "\n")]))
            elif kind == "output_ai":
                # 不要展开 ANSI！
                output_parts.append(format_ai_output(text))  # 返回 ANSI 对象
            elif kind == "output_error":
                output_parts.append(FormattedText([('class:error', text + "\n")]))
            elif kind == "output_warning":
                output_parts.append(FormattedText([('class:warning', text + "\n")]))
            elif kind == "output_info":
                output_parts.append(FormattedText([('class:info', text + "\n")]))
            elif kind in ["output_tool_title", "output_tool_result", "output_tool_error"]:
                output_parts.append(HTML(text + "\n"))
            elif kind == "output_tool_patch":
                output_parts.append(format_patch_output(text))
            elif kind == "output_base_execute_result":
                output_parts.append(format_base_execute_tool_output(text))
        return output_parts

    async def _get_user_input_pending_part(self):
        # 是否有pending
        user_input_pending_parts = []
        user_pending_inputs = await GlobalState.get_user_input_queue().peek_all()

        if user_pending_inputs and len(user_pending_inputs) > 0:
            # 先来俩换行
            user_input_pending_parts.append(FormattedText([('', "\n\n")]))
            for index, user_pending_input in enumerate(user_pending_inputs):
                # 第一行有点样式
                if index == 0:
                    user_input_pending_parts.append(FormattedText([('class:user', " > " + user_pending_input + "\n")]))
                else:
                    user_input_pending_parts.append(FormattedText([('class:user', "   " + user_pending_input + "\n")]))

        return user_input_pending_parts

    async def _get_todo_part(self):
        todo_parts = []
        if self.todo_lines and len(self.todo_lines) > 0:
            todo_parts = [format_todo_list(self.todo_lines)]
        # 如果有待办，添加俩换行
        if todo_parts and len(todo_parts) > 0:
            todo_parts.insert(0, FormattedText([('', "\n\n")]))
        return todo_parts

    async def _process_user_interrupt(self, event: Event):
        """处理用户手动中断事件"""
        # 主要还是对Pending中的消息进行处理
        input_buffer = self.cli.input_window.input_buffer
        pending_inputs = await GlobalState.get_user_input_queue().pop_all()
        if pending_inputs:
            agent_logger.info("[User interrupt]: reset user pending to input buffer")
            input_buffer.text = "\n".join(pending_inputs)
        else:
            agent_logger.info("[User interrupt]: clear input buffer")
            input_buffer.text = ""
        self.refresh()



