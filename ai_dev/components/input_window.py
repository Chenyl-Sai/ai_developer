from prompt_toolkit.layout import Dimension
from ai_dev.components.common_window import CommonWindow
from prompt_toolkit.widgets import TextArea
from wcwidth import wcwidth
from ai_dev.utils.logger import agent_logger


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

    def set_buffer_editable(self, editable: bool):
        self.window.read_only = not editable

    def set_text(self, text):
        self.window.text = text

    def get_text(self):
        return self.window.text.strip()