#!/usr/bin/env python3
"""
ScrollableFormattedTextControl 使用示例

这个示例展示了如何使用 ScrollableFormattedTextControl 创建一个上下分区的界面：
- 上方：使用 ScrollableFormattedTextControl 显示可滚动的内容
- 下方：使用 BufferControl 输入内容，输入后内容会添加到上方显示
"""

import asyncio
from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout import (
    Layout, HSplit, Window, BufferControl, WindowAlign,
    ConditionalContainer
)
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.layout.controls import FormattedTextControl
from typing import List, Tuple

from ai_dev.components.scrollable_formatted_text_control import ScrollableFormattedTextControl


class ScrollableExample:
    def __init__(self):
        # 存储显示的内容
        self.output_lines: List[str] = []

        # 输入缓冲区
        self.input_buffer = Buffer(
            multiline=False,
            on_text_changed=self._on_input_changed
        )

        # 初始化组件
        self._initialize_components()
        self._setup_keybindings()

        # 添加一些初始内容
        self._add_initial_content()

    def _initialize_components(self):
        """初始化prompt_toolkit组件"""
        # 输出控制 - 使用 ScrollableFormattedTextControl
        self.output_control = ScrollableFormattedTextControl(
            self._get_output_text,
            focusable=True
        )

        # 输入控制
        self.input_control = BufferControl(
            buffer=self.input_buffer,
            focusable=True
        )

        # 创建窗口
        self.output_window = Window(
            self.output_control,
            style="class:output"
        )

        self.input_window = Window(
            self.input_control,
            height=3,
            style="class:input"
        )

        # 分隔线
        self.separator = Window(
            FormattedTextControl(lambda: [("class:separator", "─" * 80)]),
            height=1,
            align=WindowAlign.CENTER,
            style="class:separator"
        )

        # 布局
        self.layout = Layout(
            HSplit([
                self.output_window,
                self.separator,
                Window(
                    FormattedTextControl(lambda: [("class:prompt", "输入内容 (按 Enter 发送, Ctrl+C 退出):")]),
                    height=1,
                    style="class:prompt"
                ),
                self.input_window
            ]),
            focused_element=self.input_window,  # 默认焦点在输入框
        )

    def _setup_keybindings(self):
        """设置按键绑定"""
        self.kb = KeyBindings()

        @self.kb.add("c-c")
        def _(event):
            """Ctrl+C 退出"""
            event.app.exit()

        @self.kb.add("up")
        def _(event):
            """向上滚动"""
            self.output_control.scroll_up()

        @self.kb.add("down")
        def _(event):
            """向下滚动"""
            self.output_control.scroll_down()

        @self.kb.add("pageup")
        def _(event):
            """向上翻页"""
            for _ in range(10):
                if not self.output_control.scroll_up():
                    break

        @self.kb.add("pagedown")
        def _(event):
            """向下翻页"""
            for _ in range(10):
                if not self.output_control.scroll_down():
                    break

        @self.kb.add("end")
        def _(event):
            """滚动到底部"""
            self.output_control.scroll_to_bottom()

        @self.kb.add("enter")
        def _(event):
            """回车发送消息"""
            text = self.input_buffer.text.strip()
            if text:
                self._add_output_line(f"用户输入: {text}")
                self.input_buffer.reset()

    def _get_output_text(self) -> List[Tuple[str, str]]:
        """获取格式化输出文本"""
        result = []
        for i, line in enumerate(self.output_lines):
            # 简单的样式：偶数行用默认样式，奇数行用不同样式
            style_class = "class:output-line-even" if i % 2 == 0 else "class:output-line-odd"
            result.append((style_class, line + "\n"))

        return result

    def _on_input_changed(self, buffer):
        """输入文本变化时的回调"""
        pass

    def _add_output_line(self, text: str):
        """添加输出行"""
        self.output_lines.append(text)

    def _add_initial_content(self):
        """添加初始内容"""
        initial_content = [
            "欢迎使用 ScrollableFormattedTextControl 示例！",
            "",
            "这个示例展示了：",
            "- 上方区域使用 ScrollableFormattedTextControl 显示可滚动内容",
            "- 下方区域使用 BufferControl 进行输入",
            "- 输入的内容会实时添加到上方显示区域",
            "",
            "支持的快捷键：",
            "- ↑/↓: 上下滚动",
            "- PageUp/PageDown: 翻页",
            "- End: 滚动到底部",
            "- Enter: 发送消息",
            "- Ctrl+C: 退出",
            "",
            "现在尝试在下方输入一些内容吧！"
        ]

        for line in initial_content:
            self._add_output_line(line)

    async def run(self):
        """运行应用程序"""
        # 样式定义
        style = Style([
            ('output', 'bg:#000000 #ffffff'),
            ('input', 'bg:#222222 #ffffff'),
            ('prompt', '#00ff00 bold'),
            ('separator', '#888888'),
            ('output-line-even', '#ffffff'),
            ('output-line-odd', '#cccccc'),
        ])

        # 获取输出窗口实际输出内容高度，用于实现自动滚动
        def after_render(app):
            render_info = self.output_window.render_info
            if render_info:
                self.output_control.update_line_count(render_info.content_height)

        app = Application(
            layout=self.layout,
            key_bindings=self.kb,
            style=style,
            full_screen=True,
            mouse_support=True,
            after_render=after_render,
        )

        await app.run_async()


async def main():
    """主函数"""
    example = ScrollableExample()
    await example.run()


if __name__ == "__main__":
    asyncio.run(main())