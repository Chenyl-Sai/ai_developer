from ai_dev.components.scrollable_formatted_text_control import ScrollableFormattedTextControl
from prompt_toolkit.formatted_text import HTML, FormattedText, merge_formatted_text
from prompt_toolkit.layout import Window, BufferControl
from ai_dev.utils.render import format_ai_output, format_patch_output, format_base_execute_tool_output
from ai_dev.components.common_window import CommonWindow
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.buffer import Buffer


class InputWindow(CommonWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.input_buffer = Buffer(
            multiline=False
        )

        self.input_control = BufferControl(
            buffer=self.input_buffer,
            focusable=True,
            input_processors=[
                BeforeInput("> ", style="class:user")
            ]
        )

        self.window = Window(content=self.input_control, height=1)

    def set_buffer_editable(self, buffer_editable: bool):
        self.input_buffer.read_only = lambda: not buffer_editable