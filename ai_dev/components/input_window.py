import asyncio

from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from ai_dev.components.common_window import CommonWindow
from prompt_toolkit.widgets import TextArea
from wcwidth import wcwidth


class AutoResizeTextArea(TextArea):
    def __init__(self, min_height=1, max_height=10, **kwargs):
        super().__init__(**kwargs)
        self.min_height = min_height
        self.max_height = max_height
        self.window.height = self._dynamic_height

    def _dynamic_height(self):
        estimated_wraps = 0
        render_info = self.window.render_info
        if render_info:
            width = render_info.window_width
            lines = self.text.splitlines()
            available_width = max(1, width - 2)

            for line in lines:
                line_width = sum((wcwidth(ch) or 0) for ch in line)
                wraps = (line_width // available_width)
                estimated_wraps += wraps

        manual_lines = self.text.count("\n") + 1
        total = manual_lines + estimated_wraps
        return min(total if total > 0 else 1, 20)


class InputWindow(CommonWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.window = AutoResizeTextArea(
            prompt="> ",
            multiline=True,
            wrap_lines=True,
        )
        self.input_kb = KeyBindings()
        self._setup_input_keybindings()

    def _setup_input_keybindings(self):
        @self.input_kb.add(Keys.Enter)
        async def handle_enter(event):
            """处理回车键"""
            text = self.get_text()
            if not text:
                return

            # 清空输入框
            self.set_text("")
            # 重置自动滚动状态
            self.cli.output_window.set_auto_scroll(True)

            input_type = await self.cli.process_user_input(text)

            if input_type == "Input":
                # 调度异步任务
                asyncio.create_task(self.cli.process_stream_input(text))

    def get_input_kb(self):
        return self.input_kb

    def set_buffer_editable(self, editable: bool):
        self.window.read_only = not editable

    def set_text(self, text):
        self.window.text = text

    def get_text(self):
        return self.window.text.strip()