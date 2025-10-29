import asyncio
import uuid, ast
import time
import random

from ai_dev.components.scrollable_formatted_text_control import ScrollableFormattedTextControl
from prompt_toolkit.formatted_text import FormattedText, merge_formatted_text
from prompt_toolkit.layout import Window

from ai_dev.constants.product import MAIN_AGENT_ID
from ai_dev.core.global_state import GlobalState
from ai_dev.utils.render import OutputBlock, InputBlock, MessageBlock, ToolBlock, format_output_block, TaskBlock
from ai_dev.components.common_window import CommonWindow
from ai_dev.utils.todo import TodoItemStorage, get_todos
from ai_dev.utils.logger import agent_logger
from ai_dev.core.event_manager import event_manager, EventType, Event


class OutputWindow(CommonWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output_blocks: list[OutputBlock] = []
        self.output_block_dict: dict[str, OutputBlock] = {}
        self.task_block_dict: dict[str, OutputBlock] = {}
        self.todo_lines: list[TodoItemStorage] = []
        # 输出控制
        self.output_control = ScrollableFormattedTextControl(
            self._get_full_output_text,
            focusable=True,
            cli = self.cli
        )
        self.window = Window(
            content=self.output_control,
            wrap_lines=True,
            always_hide_cursor=True,
        )
        self._compensation_pending_input_running = False
        self._max_output_blocks = 100  # 限制历史输出数量
        
        # 进度指示器相关变量
        self._model_output_start_time = None
        self._random_progress_text = None
        self._token_count = 0
        self._progress_indicator_texts = [
            "Doing...", "Generating...", "Working...", "Processing...", 
            "Thinking...", "Analyzing...", "Computing...", "Calculating..."
        ]

        # Task处理进度记录相关变量
        self._task_breathe_color_controller = {}
        self._task_breathe_color_controller_running = False

        # 创建事件循环用于界面刷新展示
        self._loop = asyncio.new_event_loop()
        def start_loop(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()
        import threading
        threading.Thread(target=start_loop, args=(self._loop,), daemon=True).start()

        # 订阅用户取消事件
        event_manager.subscribe(EventType.USER_CANCEL, self._process_user_cancel)

    def set_auto_scroll(self, auto_scroll: bool):
        self.output_control.auto_scroll = auto_scroll

    async def add_common_block(self, style: str, info: str):
        self.output_blocks.append((style, info))
        await self._cleanup_old_blocks()
        self.refresh()

    async def batch_add_common_block(self, style: str, infos: list):
        for info in infos:
            self.output_blocks.append((style, info))
        await self._cleanup_old_blocks()
        self.refresh()

    async def add_user_input_block(self, user_input: str):
        block = InputBlock(id=str(uuid.uuid4()), content=user_input)
        self.output_blocks.append(block)
        await self._cleanup_old_blocks()
        self.refresh()

    async def add_stream_output(self, chunk: dict):
        """向输出面板添加流式输出的内容"""
        # 主Agent输出
        if "source" in chunk and chunk["source"] == MAIN_AGENT_ID:
            # AI 消息
            if chunk.get('type') == "message_start":
                block = MessageBlock(id=chunk['message_id'], content=" ", status="start")
                self.output_blocks.append(block)
                self.output_block_dict["message_" + chunk['message_id']] = block
                # 开始跟踪模型输出进度
                self._model_output_start_time = time.time()
                self._random_progress_text = random.choice(self._progress_indicator_texts)
                self._token_count = 0
            elif chunk.get('type') == "message_delta":
                block = self.output_block_dict.get("message_" + chunk['message_id'])
                if block:
                    block.content += chunk['delta']
                    self._token_count = chunk['estimate_tokens']
            elif chunk.get('type') == "message_end":
                block = self.output_block_dict.get("message_" + chunk['message_id'])
                if block:
                    block.status = "stop"
                # 结束跟踪模型输出进度
                self._model_output_start_time = None
                self._random_progress_text = None
                self._token_count = 0

            # 工具消息
            elif chunk.get('type') == "tool_start":
                if chunk['tool_name'] == "TodoWriteTool":
                    return
                elif chunk['tool_name'] == "TaskTool":
                    block = TaskBlock(id=chunk['tool_id'],
                                      task_id=chunk['task_id'],
                                      tool_name=chunk['tool_name'],
                                      tool_args=chunk['tool_args'],
                                      message=chunk['message'],
                                      status="start",
                                      start_time=time.time())
                    self.output_blocks.append(block)
                    self.task_block_dict["task_" + chunk['task_id']] = block
                    self._task_breathe_color_controller[block.id] = 0
                else:
                    block = ToolBlock(id=chunk['tool_id'],
                                      tool_name=chunk['tool_name'],
                                      tool_args=chunk['tool_args'],
                                      message=chunk['message'],
                                      status="start")
                    self.output_blocks.append(block)
                    self.output_block_dict["tool_" + chunk['tool_id']] = block
            elif chunk.get('type') == "tool_delta":
                if chunk['tool_name'] == "TaskTool":
                    block = self.task_block_dict.get("task_" + chunk['task_id'])
                    if block:
                        block.message = chunk['message']
                else:
                    block = self.output_block_dict.get("tool_" + chunk['tool_id'])
                    if block:
                        block.message = chunk['message']
            elif chunk.get('type') == "tool_end":
                # 对于待办工具使用做特殊处理
                if chunk['tool_name'] == "TaskTool":
                    block = self.task_block_dict.get("task_" + chunk['task_id'])
                    if block:
                        block.end_time = time.time()
                        block.message = chunk.get('message')
                        block.status = chunk.get("status")
                        block.task_response = chunk.get("result")
                        agent_logger.debug(f"Task End Chunk: {chunk}")
                        if block.id in self._task_breathe_color_controller:
                            del self._task_breathe_color_controller[block.id]
                elif chunk.get("tool_name") == "TodoWriteTool":
                    agent_id = MAIN_AGENT_ID
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
                    block = self.output_block_dict.get("tool_" + chunk['tool_id'])
                    if block:
                        block.message = chunk.get('message')
                        block.status = chunk.get("status")
                        block.exec_result_details = chunk.get("result")
        else:
            # 子任务的输出
            # 找到那个任务
            source = chunk.get("source")
            if source is None:
                agent_logger.warning(f"Chunk missing 'source' field: {chunk}")
                return

            task_block = self.task_block_dict.get("task_" + source)
            # 如果没有找到哪个task就丢了
            if not task_block:
                agent_logger.warning(f"Chunk does not fount its parent task block: {chunk}")
                return

            # AI 消息
            if chunk.get('type') == "message_start":
                block = MessageBlock(id=chunk['message_id'], content=" ", status="start")
                task_block.process_blocks.append(block)
                task_block.process_block_dict["message_" + chunk['message_id']] = block
            elif chunk.get('type') == "message_delta":
                block = task_block.process_block_dict.get("message_" + chunk['message_id'])
                if block:
                    block.content += chunk['delta']
                    self._token_count = chunk['estimate_tokens']
            elif chunk.get('type') == "message_end":
                block = task_block.process_block_dict.get("message_" + chunk['message_id'])
                if block:
                    block.status = "stop"

            # 工具消息
            elif chunk.get('type') == "tool_start":
                block = ToolBlock(id=chunk['tool_id'],
                                  tool_name=chunk['tool_name'],
                                  tool_args=chunk['tool_args'],
                                  message=chunk['message'],
                                  status="start")
                task_block.tool_ids.add(chunk['tool_id'])
                task_block.process_blocks.append(block)
                task_block.process_block_dict["tool_" + chunk['tool_id']] = block
            elif chunk.get('type') == "tool_delta":
                block = task_block.process_block_dict.get("tool_" + chunk['tool_id'])
                if block:
                    block.message = chunk['message']
            elif chunk.get('type') == "tool_end":
                block = task_block.process_block_dict.get("tool_" + chunk['tool_id'])
                if block:
                    block.message = chunk.get('message')
                    block.status = chunk.get("status")
                    block.exec_result_details = chunk.get("result")

        self.refresh()

    async def remove_recently_user_input_block(self, text: str):
        for i in range(len(self.output_blocks) - 1, -1, -1):  # 倒序遍历索引
            if isinstance(self.output_blocks[i], InputBlock) and self.output_blocks[i].content == text:
                del self.output_blocks[i]
                break
        self.refresh()

    async def user_pending_input_consumed(self, user_inputs: list[str]):
        user_input = "\n".join(user_inputs)
        await self.add_user_input_block(user_input)

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

    async def task_breathe_color_controller_loop(self):
        self._task_breathe_color_controller_running = True

        try:
            while self._task_breathe_color_controller_running:
                if self._task_breathe_color_controller:
                    for task_id, color in self._task_breathe_color_controller.items():
                        if color == 0:
                            self._task_breathe_color_controller.update({task_id: 1})
                        else:
                            self._task_breathe_color_controller.update({task_id: 0})
                    # 刷新一下
                    self.refresh()
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            self._task_breathe_color_controller_running = False

    def _get_full_output_text(self):
        result = []
        result.extend(asyncio.run_coroutine_threadsafe(self._get_output_part(), self._loop).result())
        result.extend(asyncio.run_coroutine_threadsafe(self._get_user_input_pending_part(), self._loop).result())
        result.extend(asyncio.run_coroutine_threadsafe(self._get_todo_part(), self._loop).result())
        return merge_formatted_text(result)

    async def _get_output_part(self):
        result = []
        for block in self.output_blocks:
            result.append(await format_output_block(block, self._task_breathe_color_controller))
            # 每个block之间添加一个换行
            result.append(FormattedText([("", " \n")]))
        return result

    async def _get_user_input_pending_part(self):
        # 是否有pending
        user_input_pending_parts = []
        user_pending_inputs = await GlobalState.get_user_input_queue().peek_all()

        if user_pending_inputs and len(user_pending_inputs) > 0:
            # 先来俩换行
            user_input_pending_parts.append(FormattedText([('', " \n \n")]))
            for index, user_pending_input in enumerate(user_pending_inputs):
                # 第一行有点样式
                if index == 0:
                    user_input_pending_parts.append(FormattedText([('class:user', "> " + user_pending_input + "\n")]))
                else:
                    user_input_pending_parts.append(FormattedText([('class:user', "  " + user_pending_input + "\n")]))

        return user_input_pending_parts

    async def _get_todo_part(self):
        result = []

        # 对todos排序
        def sort_key(item):
            status_order = {"completed": 0, "in_progress": 1, "pending": 2}
            priority_order = {"high": 0, "medium": 1, "low": 2}
            return (
                status_order.get(item.status, 3),
                item.create_at,
                priority_order.get(item.priority, 3),
            )

        if self.todo_lines:
            self.todo_lines.sort(key=sort_key)

            # 检查是否有正在进行的模型输出
            doing = next((todo.content for todo in self.todo_lines if todo.status == 'in_progress'), None)
            # 有正在做的待办
            if doing:
                # 当前正在做的
                result.append(("class:common.pink", f" * {doing}...（{self._get_progress_info()})\n"))
            # 展示列表
            for todo in self.todo_lines:
                status = todo.status
                if status == "completed":
                    result.append(("class:common.gray", f"  ☒ {todo.content}\n"))
                elif status == "in_progress":
                    result.append(("bold", f"  ☐ {todo.content}\n"))
                elif status == "pending":
                    result.append(("", f"  ☐ {todo.content}\n"))
        elif self._model_output_start_time is not None:
            # 没有待办列表, 随机选择一个进度文本
            result.append(("class:common.pink", f" * {self._random_progress_text}({self._get_progress_info()})"))
        return [FormattedText(result)]

    async def _cleanup_old_blocks(self):
        """清理旧的输出块，防止内存累积"""
        if len(self.output_blocks) > self._max_output_blocks:
            # 保留最新的输出块
            keep_count = self._max_output_blocks // 2  # 保留一半
            remove_count = len(self.output_blocks) - keep_count
            
            # 清理output_blocks
            removed_blocks = self.output_blocks[:remove_count]
            self.output_blocks = self.output_blocks[remove_count:]
            
            # 清理对应的output_block_dict
            for block in removed_blocks:
                if isinstance(block, MessageBlock):
                    self.output_block_dict.pop(f"message_{block.id}", None)
                elif isinstance(block, ToolBlock):
                    self.output_block_dict.pop(f"tool_{block.id}", None)
            
            agent_logger.debug(f"清理了 {remove_count} 个旧的输出块")

    async def _process_user_cancel(self, event: Event):
        """处理用户手动中断事件"""
        # 主要还是对Pending中的消息进行处理
        pending_inputs = await GlobalState.get_user_input_queue().pop_all()
        if pending_inputs:
            self.cli.input_window.set_text("\n".join(pending_inputs))
        else:
            self.cli.input_window.set_text("")
        self.refresh()

    def _get_progress_info(self) -> str:
        """获取进度信息（持续时间和token数量）"""
        if self._model_output_start_time is None:
            return ""
        duration = int(time.time() - self._model_output_start_time)
        if self._token_count < 1000:
            token_str = str(self._token_count)
        else:
            token_str = f"{self._token_count / 1000:.1f}k"

        return f"{duration} s · ↓ {token_str} tokens"
