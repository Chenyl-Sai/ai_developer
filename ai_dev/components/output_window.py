import asyncio
import uuid, ast

from ai_dev.components.scrollable_formatted_text_control import ScrollableFormattedTextControl
from prompt_toolkit.formatted_text import FormattedText, merge_formatted_text
from prompt_toolkit.layout import Window

from ai_dev.constants.product import MAIN_AGENT_NAME
from ai_dev.core.global_state import GlobalState
from ai_dev.utils.render import \
    format_todo_list, OutputBlock, InputBlock, MessageBlock, ToolBlock, format_output_block
from ai_dev.components.common_window import CommonWindow
from ai_dev.utils.todo import TodoItemStorage, get_todos
from ai_dev.utils.logger import agent_logger
from ai_dev.core.event_manager import event_manager, EventType, Event


class OutputWindow(CommonWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output_blocks: list[OutputBlock] = []
        self.output_block_dict: dict[str, OutputBlock] = {}
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

    async def add_common_block(self, style: str, info: str):
        self.output_blocks.append((style, info))

    async def batch_add_common_block(self, style: str, infos: list):
        for info in infos:
            self.output_blocks.append((style, info))

    async def add_user_input_block(self, user_input: str):
        block = InputBlock(id=str(uuid.uuid4()), content=user_input)
        self.output_blocks.append(block)

    async def add_stream_output(self, chunk: dict):
        """向输出面板添加流式输出的内容"""
        # AI 消息
        if chunk.get('type') == "message_start":
            block = MessageBlock(id=chunk['message_id'], content="", status="start")
            self.output_blocks.append(block)
            self.output_block_dict["message_" + chunk['message_id']] = block
        elif chunk.get('type') == "message_delta":
            block = self.output_block_dict["message_" + chunk['message_id']]
            block.content += chunk['delta']
        elif chunk.get('type') == "message_end":
            self.output_block_dict["message_" + chunk['message_id']]["status"] = "stop"

        # 工具消息
        elif chunk.get('type') == "tool_start":
            block = ToolBlock(id=chunk['tool_id'],
                              tool_name=chunk['tool_name'],
                              tool_args=chunk['shown_tool_args'],
                              message=chunk['message'],
                              status="start")
            self.output_blocks.append(block)
            self.output_block_dict["tool_" + chunk['tool_id']] = block
        elif chunk.get('type') == "tool_delta":
            block = self.output_block_dict["tool_" + chunk['tool_id']]
            block.message = chunk['message']
        elif chunk.get('type') == "tool_end":
            # 对于待办工具使用做特殊处理
            if chunk.get("tool_name") == "TodoWriteTool":
                agent_id = MAIN_AGENT_NAME
                context = chunk.get("context", {})
                if context and "agent_id" in context:
                    if len(context.get("agent_id")) > 0:
                        agent_id = context.get("agent_id")
                todos = await get_todos(agent_id)
                # 如果全部都完成了，就不添加了
                remains = [todo for todo in todos if todo.status != 'completed']
                if len(remains) == 0:
                    todos = []
                self.todo_lines = todos
            else:
                block = self.output_block_dict["tool_" + chunk['tool_id']]
                block.message = chunk.get('message')
                block.status = chunk.get("status")
                block.exec_result_details = chunk.get("result")
        self.refresh()

    async def remove_recently_user_input_block(self, text: str):
        async with self.output_lock:
            for i in range(len(self.output_blocks) - 1, -1, -1):  # 倒序遍历索引
                if isinstance(self.output_blocks[i], InputBlock) and self.output_blocks[i].content == text:
                    del self.output_blocks[i]
                    break
        self.refresh()

    async def user_pending_input_consumed(self, user_inputs: list[str]):
        user_input = "\n".join(user_inputs)
        await self.add_user_input_block(user_input)

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
                        await self.user_pending_input_consumed(pending_inputs)
                        await self.cli.process_stream_input("\n".join(pending_inputs))
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        finally:
            self._compensation_pending_input_running = False

    async def _get_output_part(self):
        result = []
        for block in self.output_blocks:
            result.append(await format_output_block(block))
            # 每个block之间添加一个换行
            result.append(FormattedText([("", "\n")]))
        return result

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
                    user_input_pending_parts.append(FormattedText([('class:user', "> " + user_pending_input + "\n")]))
                else:
                    user_input_pending_parts.append(FormattedText([('class:user', "  " + user_pending_input + "\n")]))

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
        pending_inputs = await GlobalState.get_user_input_queue().pop_all()
        if pending_inputs:
            agent_logger.info("[User interrupt]: reset user pending to input buffer")
            self.cli.input_window.set_text("\n".join(pending_inputs))
        else:
            agent_logger.info("[User interrupt]: clear input buffer")
            self.cli.input_window.set_text("")
        self.refresh()
