from prompt_toolkit.layout import FormattedTextControl
from prompt_toolkit.data_structures import Point
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
        self._line_count = 0

    def _get_cursor_position(self) -> Point:
        """获取光标位置控制滚动"""
        if self._line_count == 0:
            return Point(0, 0)
        return Point(0, self.cursor_position)

    def scroll_to_bottom(self):
        """滚动到底部"""
        if self._line_count > 0:
            self.cursor_position = self._line_count - 1
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
        if self._line_count > 0 and self.cursor_position < self._line_count - 1:
            self.cursor_position += 1
            return True
        # 如果已经在最底部，重新启用自动滚动
        if self._line_count > 0 and self.cursor_position >= self._line_count - 1:
            self.auto_scroll = True
        return False

    def update_line_count(self, line_count: int):
        """更新行数并自动滚动"""
        self._line_count = line_count
        if self.auto_scroll:
            self.scroll_to_bottom()