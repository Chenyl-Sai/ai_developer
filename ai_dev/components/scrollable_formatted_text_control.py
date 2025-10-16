from prompt_toolkit.layout import FormattedTextControl
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text.utils import (
    split_lines,
)
from typing import Callable, Optional, List, Tuple, Any


class ScrollableFormattedTextControl(FormattedTextControl):
    """
    支持滚动和自动滚到底部的 FormattedTextControl
    """

    def __init__(
        self,
        text: Callable[[], List[Tuple[str, str]]],
        *args,
        **kwargs
    ):
        super().__init__(text=text, get_cursor_position = self._get_cursor_position, *args, **kwargs)
        self.auto_scroll = True
        self.cursor_position = 0
        self.last_line_count = 0
        self.current_line_count = 0

    def _get_cursor_position(self) -> Point:
        """获取光标位置控制滚动"""
        # 获取光标的时候计算几下当前绘制高度
        self.current_line_count = self.get_line_count()
        if self.current_line_count == 0:
            return Point(0, 0)
        safe_position = min(self.cursor_position, max(0, self.current_line_count - 1))
        return Point(0, safe_position)

    def scroll_to_bottom(self):
        """滚动到底部"""
        if self.current_line_count > 0:
            self.cursor_position = self.current_line_count - 1
            self.auto_scroll = True

    def scroll_up(self) -> bool:
        """向上滚动"""
        if self.cursor_position > 0:
            self.cursor_position -= 1
            self.auto_scroll = False
            return True
        return False

    def scroll_down(self) -> bool:
        """向下滚动"""
        if self.current_line_count > 0 and self.cursor_position < self.current_line_count - 1:
            self.cursor_position += 1
            return True
        # 如果已经在最底部，重新启用自动滚动
        if self.current_line_count > 0 and self.cursor_position >= self.current_line_count - 1:
            self.auto_scroll = True
        return False

    def get_line_count(self):
        fragment_lines_with_mouse_handlers = list(split_lines(super()._get_formatted_text_cached()))
        fragment_lines: list = [
            [(item[0], item[1]) for item in line]
            for line in fragment_lines_with_mouse_handlers
        ]
        self.current_line_count = len(fragment_lines)
        # 如果发现行数更新了，且自动滚动，滚动光标
        if self.current_line_count != self.last_line_count and self.auto_scroll:
            self.scroll_to_bottom()
        self.last_line_count = self.current_line_count
        return self.current_line_count