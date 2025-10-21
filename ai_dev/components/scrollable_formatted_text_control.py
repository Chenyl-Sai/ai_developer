from prompt_toolkit.clipboard import ClipboardData
from prompt_toolkit.layout import FormattedTextControl
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text.utils import (
    split_lines,
)
from typing import Callable, Optional, List, Tuple, Any

from prompt_toolkit.mouse_events import MouseEvent, MouseEventType, MouseButton
from prompt_toolkit.application import get_app

import time

from ai_dev.utils.logger import agent_logger


class ScrollableFormattedTextControl(FormattedTextControl):
    """
    支持滚动和自动滚到底部的 FormattedTextControl
    """

    def __init__(
        self,
        text: Callable[[], List[Tuple[str, str]]],
        cli,
        *args,
        **kwargs
    ):
        super().__init__(text=text, get_cursor_position = self._get_cursor_position, *args, **kwargs)
        self.cli = cli
        # 滚动控制
        self.auto_scroll = True
        self.cursor_position = 0
        self.last_line_count = 0
        self.current_line_count = 0

        # 选中控制
        self._selection_start: Optional[int] = None
        self._selection_end: Optional[int] = None
        self._last_click_timestamp: Optional[float] = None
        self._is_selecting = False
        self._highlight_style = "reverse"

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

    def _get_parent_window(self):
        # 查找包含当前 control 的窗口
        for window in get_app().layout.find_all_windows():
            if window.content == self:
                return window
        return None

    def get_visible_range(self) -> Tuple[int, int]:
        """获取当前可见区域的第一行和最后一行索引
        
        Returns:
            Tuple[int, int]: (first_visible_line, last_visible_line)
        """
        app = get_app()
        layout = app.layout
        
        # 查找包含当前 control 的窗口
        window_info = self._get_parent_window()
        
        if not window_info or not window_info.render_info:
            return 0, 0
            
        # 获取窗口的可见区域高度
        _rowcol_to_yx = window_info.render_info._rowcol_to_yx if window_info.render_info._rowcol_to_yx else None
        first_visible_line = None
        last_visible_line = None
        if _rowcol_to_yx and len(_rowcol_to_yx) > 0:
            for rowcol, _ in _rowcol_to_yx.items():
                row = rowcol[0]
                if first_visible_line is None or first_visible_line > row:
                    first_visible_line = row
                if last_visible_line is None or last_visible_line < row:
                    last_visible_line = row
        return (first_visible_line if first_visible_line else 0,
                last_visible_line if last_visible_line else self.current_line_count - 1)

    def move_cursor_up(self) -> bool:
        """向上滚动"""
        # 获取当前可见区域
        first_visible, last_visible = self.get_visible_range()
        # 将光标移动到可见区域的第一行
        if self.cursor_position > first_visible:
            self.cursor_position = first_visible

        if self.cursor_position > 0:
            self.cursor_position -= 1
            self.auto_scroll = False
            return True
        return False

    def move_cursor_down(self) -> bool:
        """向下滚动"""
        # 获取当前可见区域
        first_visible, last_visible = self.get_visible_range()
        # 将光标移动到可见区域的最后一行再向下滚动一行
        if self.cursor_position < last_visible:
            self.cursor_position = last_visible

        if self.current_line_count > 0 and self.cursor_position < self.current_line_count - 1:
            self.cursor_position += 1
            return True
        # 如果已经在最底部，重新启用自动滚动
        if self.current_line_count > 0 and self.cursor_position >= self.current_line_count - 1:
            self.cursor_position = self.current_line_count - 1
            self.auto_scroll = True
        return False

    def get_line_count(self):
        fragment_lines_with_mouse_handlers = list(split_lines(super()._get_formatted_text_cached()))
        fragment_lines: list = [
            [(item[0], item[1]) for item in line]
            for line in fragment_lines_with_mouse_handlers
        ]
        self.current_line_count = len(fragment_lines) - 1
        # 如果发现行数更新了，且自动滚动，滚动光标
        if self.current_line_count != self.last_line_count and self.auto_scroll:
            self.scroll_to_bottom()
        self.last_line_count = self.current_line_count
        return self.current_line_count

    def mouse_handler(self, mouse_event: MouseEvent):
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            if self.move_cursor_down():
                get_app().invalidate()
            return None
        elif mouse_event.event_type == MouseEventType.SCROLL_UP:
            if self.move_cursor_up():
                get_app().invalidate()
            return None
        elif mouse_event.event_type == MouseEventType.MOUSE_DOWN:
            position = mouse_event.position
            char_index = self._get_char_index_at_position(position.x, position.y)

            if char_index is None:
                return

            self.clear_selection()
            self._selection_start = char_index
            self._selection_end = char_index
            self._is_selecting = True

            # 处理双击选择单词
            double_click = (
                    self._last_click_timestamp
                    and time.time() - self._last_click_timestamp < 0.3
            )
            self._last_click_timestamp = time.time()

            if double_click:
                # 简单的单词选择逻辑
                formatted_text = super()._get_formatted_text_cached()
                if formatted_text:
                    plain_text = ''.join(
                        fragment[1] if isinstance(fragment, tuple) and len(fragment) > 1 else str(fragment)
                        for fragment in formatted_text
                    )

                    # 查找单词边界
                    start = char_index
                    end = char_index

                    # 向左查找单词开始
                    while start > 0 and plain_text[start - 1].isalnum():
                        start -= 1

                    # 向右查找单词结束
                    while end < len(plain_text) - 1 and plain_text[end + 1].isalnum():
                        end += 1

                    self._selection_start = start
                    self._selection_end = end

            get_app().invalidate()
            return None
        # 处理鼠标移动事件 - 扩展选择
        elif (mouse_event.event_type == MouseEventType.MOUSE_MOVE and
              self._is_selecting and mouse_event.button != MouseButton.NONE):
            position = mouse_event.position
            char_index = self._get_char_index_at_position(position.x, position.y)

            if char_index is None:
                return
            self._selection_end = char_index

            get_app().invalidate()
            return None

        # 处理鼠标释放事件 - 结束选择
        elif mouse_event.event_type == MouseEventType.MOUSE_UP:
            self._is_selecting = False

            # 选择完了之后设置一下当前control所在的window为layout的焦点
            window = self._get_parent_window()
            if window:
                get_app().layout.focus(window)

            # 如果点击但没有拖动，清除选择
            if self._selection_start == self._selection_end:
                self.clear_selection()

            get_app().invalidate()
            return None

        return NotImplemented


    def _get_char_index_at_position(self, x: int, y: int) -> Optional[int]:
        """
        将屏幕坐标转换为文本中的字符索引
        """
        # 获取格式化文本内容
        formatted_text = super()._get_formatted_text_cached()
        if not formatted_text:
            return None
        content_fragments = list(formatted_text)
        # 将格式化文本转换为纯文本以便计算索引
        plain_text = self._get_plain_text(content_fragments)
        lines = plain_text.splitlines()

        # 检查坐标是否在有效范围内
        if y < 0 or y >= len(lines) or x < 0 or x >= len(lines[y]):
            return None

        char_index = 0
        for i in range(y):
            char_index += len(lines[i]) + 1  # +1 for newline
        char_index += x
        return min(char_index, len(plain_text) - 1) if plain_text else None

    def _get_plain_text(self, formatted_text) -> str:
        """将格式化文本转换为纯文本"""
        return ''.join(
            fragment[1] if isinstance(fragment, tuple) else fragment
            for fragment in formatted_text
        )


    @property
    def selected_text(self) -> str:
        """获取当前选中的文本"""
        if self._selection_start is None or self._selection_end is None:
            return ""

        formatted_text = super()._get_formatted_text_cached()
        if not formatted_text:
            return ""

        # 将格式化文本转换为纯文本
        plain_text = self._get_plain_text(formatted_text)

        start = min(self._selection_start, self._selection_end)
        end = max(self._selection_start, self._selection_end)

        return plain_text[start:end + 1] if start <= end else ""

    def clear_selection(self):
        """清除选择"""
        self._selection_start = None
        self._selection_end = None
        self._is_selecting = False
        self.cli.process_focus()


    def _get_formatted_text_cached(self):
        """获取带选择高亮的格式化文本"""
        # 获取原始格式化文本
        original_text = super()._get_formatted_text_cached()
        if not original_text:
            return []

        # 如果没有选择，返回原始文本
        if self._selection_start is None or self._selection_end is None:
            return original_text

        # 将格式化文本转换为纯文本
        plain_text = self._get_plain_text(original_text)

        # 确定选择范围
        start = min(self._selection_start, self._selection_end)
        end = max(self._selection_start, self._selection_end)

        # 确保选择范围在文本范围内
        start = max(0, min(start, len(plain_text) - 1))
        end = max(0, min(end, len(plain_text) - 1))

        # 构建带高亮的新格式化文本
        result = []
        current_pos = 0

        # 处理选择前的文本
        if start > 0:
            result.extend(self._extract_fragments(original_text, 0, start))
            current_pos = start

        # 处理选中的文本（应用高亮样式）
        if start <= end:
            selected_fragments = self._extract_fragments(original_text, start, end + 1)
            for fragment in selected_fragments:
                if isinstance(fragment, tuple):
                    # 合并原有样式和高亮样式
                    original_style = fragment[0]
                    text = fragment[1]
                    # 如果原有样式是字符串，添加高亮样式
                    if isinstance(original_style, str):
                        new_style = f"{original_style} {self._highlight_style}"
                    else:
                        # 如果原有样式是样式列表，添加高亮样式
                        new_style = original_style + [self._highlight_style]

                    if len(fragment) >= 3:
                        result.append((new_style, text, fragment[2]))
                    else:
                        result.append((new_style, text))

                else:
                    # 纯文本片段，直接应用高亮样式
                    result.append((self._highlight_style, fragment))
            current_pos = end + 1

        # 处理选择后的文本
        if current_pos < len(plain_text):
            result.extend(self._extract_fragments(original_text, current_pos, len(plain_text)))

        return result

    def _extract_fragments(self, formatted_text, start: int, end: int):
        """从格式化文本中提取指定范围的片段"""
        result = []
        current_pos = 0

        for fragment in formatted_text:
            if isinstance(fragment, tuple):
                text = fragment[1]
            else:
                text = fragment

            fragment_start = current_pos
            fragment_end = current_pos + len(text)

            # 检查片段是否与目标范围重叠
            if fragment_end <= start or fragment_start >= end:
                # 无重叠，跳过
                current_pos += len(text)
                continue

            # 计算重叠部分
            overlap_start = max(fragment_start, start)
            overlap_end = min(fragment_end, end)
            overlap_text = text[overlap_start - fragment_start:overlap_end - fragment_start]

            if isinstance(fragment, tuple):
                result.append((fragment[0], overlap_text))
            else:
                result.append(overlap_text)

            current_pos += len(text)

            # 如果已经到达目标范围末尾，提前退出
            if fragment_end >= end:
                break

        return result

    def copy_selection(self):
        if len(self.selected_text) > 0:
            try:
                import pyperclip
                """复制到系统剪贴板"""
                pyperclip.copy(self.selected_text)
            except Exception as e:
                agent_logger.error("Copy selection to system error", exception=e)
                get_app().clipboard.settext(self.selected_text)
            return ClipboardData(self.selected_text)
        return None
