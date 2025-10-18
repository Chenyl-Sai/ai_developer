from prompt_toolkit.formatted_text import FormattedText, merge_formatted_text
from prompt_toolkit.layout import Window
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys

from ai_dev.components.common_window import CommonWindow
from ai_dev.components.scrollable_formatted_text_control import ScrollableFormattedTextControl
from ai_dev.core.event_manager import event_manager, Event, EventType
from ai_dev.utils.logger import agent_logger

import asyncio

class ChoiceWindow(CommonWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.choice_content: FormattedText | None = None
        self.choice_options: list = []
        self.current_choice_index: int = 0

        self.choice_control = ScrollableFormattedTextControl(
            self._get_choice_text,
            focusable=True,
        )
        self.window = Window(
            content=self.choice_control
        )
        self.show_choice=False
        self.choice_kb = KeyBindings()
        self._setup_keybindings()

    def set_choice_content(self, choice_content: FormattedText):
        self.choice_content = choice_content

    def set_choice_options(self, choice_options: list):
        self.choice_options = choice_options

    def set_show_choice(self, show_choice: bool):
        self.show_choice = show_choice

    def need_show(self):
        return self.show_choice

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

        @self.choice_kb.add(Keys.Escape)
        def handle_escape(event):
            asyncio.create_task(self._handle_choice_input("3"))

        @self.choice_kb.add(Keys.Up)
        def handle_choice_up(event):
            # 优先滚动
            if self.choice_control and self.choice_control.scroll_up():
                event.app.invalidate()
            # 无法滚动了调整选项
            elif self.current_choice_index > 0:
                self.current_choice_index -= 1
                event.app.invalidate()

        @self.choice_kb.add(Keys.Down)
        def handle_choice_down(event):
            if self.choice_control and self.choice_control.scroll_down():
                event.app.invalidate()
            elif self.current_choice_index < len(self.choice_options) - 1:
                self.current_choice_index += 1
                event.app.invalidate()

        @self.choice_kb.add(Keys.Enter)
        def handle_choice_enter(event):
            asyncio.create_task(self._handle_choice_input(str(self.current_choice_index + 1)))

    def _get_choice_text(self):
        parts = []
        parts.append(self.choice_content)
        for index, option in enumerate(self.choice_options):
            if index == self.current_choice_index:
                parts.append(FormattedText([('class:common.blue', "  > " + option + "\n")]))
            else:
                parts.append(FormattedText([("", "    " + option + "\n")]))
        return merge_formatted_text(parts)

    async def _handle_choice_input(self, choice: str):
        """处理选择输入"""
        if choice not in ['1', '2', '3']:
            await self.cli.output_window.add_common_block("class:error", "❌ 请输入 1、2 或 3")
            return

        if choice == '3':
            import time
            await event_manager.publish(Event(
                event_type=EventType.INTERRUPT,
                data={
                    "source": "keyboard",
                },
                source="AdvancedCLI",
                timestamp=time.time()
            ))

        # 恢复输入框
        self.set_show_choice(False)
        self.cli.re_construct_layout()

        # 处理选择结果
        await self._handle_interruption_recovery(choice)

    async def _handle_interruption_recovery(self, recovery_input: str):
        """处理中断恢复"""
        try:
            agent_logger.info(f"开始处理中断恢复: {recovery_input}")

            await self.cli.process_stream_input(recovery_input)

            agent_logger.info(f"中断恢复处理完成: {recovery_input}")
        except Exception as e:
            await self.cli.output_window.add_common_block("class:error", f"Error: {e}")
            agent_logger.log_agent_error("interruption_recovery", str(e), e, {
                "recovery_input": recovery_input,
                "stage": "interruption_recovery"
            })