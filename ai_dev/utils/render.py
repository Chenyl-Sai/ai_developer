from prompt_toolkit.formatted_text import FormattedText, AnyFormattedText, HTML, merge_formatted_text
from typing import Any, TypedDict, Union
from pydantic import BaseModel

import ast
from ai_dev.constants.product import MAIN_AGENT_NAME
from ai_dev.utils.todo import get_todos, TodoItemStorage
from ai_dev.utils.logger import agent_logger


class InputBlock(BaseModel):
    id: str
    content: str


class MessageBlock(BaseModel):
    id: str
    content: str | None = None
    status: str | None = None


class ToolBlock(BaseModel):
    id: str
    tool_name: str
    tool_args: str | None
    status: str | None = None
    message: str | None = None
    exec_result_details: Any | None = None
    context: dict | None = None


OutputBlock = Union[str, tuple[str, str], InputBlock, MessageBlock, ToolBlock]


def format_ai_output(text):
    """将Markdown文本转换为ANSI格式用于终端显示
    
    Args:
        text (str): Markdown格式文本
        
    Returns:
        ANSI: prompt_toolkit的ANSI格式对象
    """
    from rich.console import Console
    from rich.markdown import Markdown
    from io import StringIO
    from prompt_toolkit.formatted_text import ANSI

    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, color_system="truecolor")
    console.print(Markdown(text))
    ansi_text = buffer.getvalue()
    return ANSI(ansi_text)


async def format_output_block(block: OutputBlock) -> AnyFormattedText:
    # 默认样式字符串
    if isinstance(block, str):
        return FormattedText([("", block)])
    # 带样式的
    elif isinstance(block, tuple):
        return FormattedText([block])
    # 用户输入
    elif isinstance(block, InputBlock):
        return FormattedText([("class:user", f"> {block.content}")])
    # AI回复
    elif isinstance(block, MessageBlock):
        prefix = FormattedText([("fg:white", "⏺ ")])
        return merge_formatted_text([prefix, format_ai_output(block.content)])
    # 工具执行
    elif isinstance(block, ToolBlock):
        return await format_tool_block(block)


async def format_tool_block(block: ToolBlock) -> AnyFormattedText:
    tool_status = block.status
    # 工具开始执行 & 执行过程中
    if tool_status == "start":
        # 展示标题
        html_text = f"<style fg='#000000'>⏺</style> <bold>{block.tool_name}</bold>"
        if block.tool_args:
            html_text += f"({block.tool_args})"
        html_text += "\n"
        # 展示过程中的额外消息
        if block.message:
            html_text += f"  ⎿  {block.message}"
        else:
            html_text += f"  ⎿  Doing…"
        return HTML(html_text)
    # 工具执行成功
    elif tool_status == "success":
        # 展示标题，图标变色
        html_text = f"<style fg='#33ff66'>⏺</style> <bold>{block.tool_name}</bold>"
        if block.tool_args:
            html_text += f"({block.tool_args})"
        html_text += "\n"
        # 展示总结性的信息
        if block.message:
            html_text += f"  ⎿  {block.message}"
        html_text += "\n"
        html = HTML(html_text)
        # 对于一些特殊的工具需要展示执行的详情
        detail = await format_tool_exec_detail(block)
        if detail:
            return merge_formatted_text([html, detail])
        else:
            return html
    # 工具执行成功
    elif tool_status == "error":
        # 展示标题，图标变色
        html_text = f"<style fg='#ff0000'>⏺</style> <bold>{block.tool_name}</bold>"
        if block.tool_args:
            html_text += f"({block.tool_args})"
        html_text += "\n"
        # 展示总结性的信息
        if block.message:
            html_text += f"  ⎿  <style fg='#ff0000'>{block.message}</style>"
        else:
            html_text += f"  ⎿  <style fg='#ff0000'>Error</style>"
        html_text += "\n"
        html = HTML(html_text)
        # 对于一些特殊的工具需要展示执行的详情
        detail = await format_tool_exec_detail(block)
        if detail:
            return merge_formatted_text([html, detail])
        else:
            return html


async def format_tool_exec_detail(block: ToolBlock) -> AnyFormattedText:
    tool_name = block.tool_name
    # 文件编辑 & 文件写入， 需要展示修改对比
    if tool_name in ["FileEditTool", "FileWriteTool"]:
        patch = block.exec_result_details.get("patch")
        if patch:
            return FormattedText(render_hunks(patch))
    # Bash命令执行
    elif tool_name in ["BashExecuteTool"]:
        return format_bash_execute_tool_output(block.exec_result_details)

    return None


def render_hunks(hunks: list[dict]) -> list[tuple]:
    formatted_lines = []
    # 处理每个hunk，添加间隔逻辑
    prev_hunk_end = 0
    for hunk_index, hunk in enumerate(hunks):
        # 解析当前hunk的起始行号
        header = hunk['header']
        import re
        header_match = re.match(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', header)
        if header_match:
            current_hunk_start = int(header_match.group(1))

            # 如果与前一个hunk的间隔太大，添加省略号
            if hunk_index > 0 and current_hunk_start - prev_hunk_end > 1:
                formatted_lines.append(('class:tool.patch.diff.hunk_info', "    ...\n"))

            prev_hunk_end = current_hunk_start + len([l for l in hunk['lines'] if not l.startswith('+')])

        # 渲染当前hunk
        formatted_lines.extend(render_hunk(hunk=hunk))
    return formatted_lines


def render_hunk(hunk: dict) -> list[tuple]:
    """渲染单个hunk块"""
    lines = []

    # 解析header获取行号信息
    header = hunk['header']
    # 解析类似 "@@ -38,8 +38,7 @@" 的格式
    import re
    header_match = re.match(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', header)

    old_start = int(header_match.group(1))
    old_count = int(header_match.group(2)) if header_match.group(2) else 1
    new_start = int(header_match.group(3))
    new_count = int(header_match.group(4)) if header_match.group(4) else 1

    # 处理hunk中的每一行
    old_line_no = old_start
    new_line_no = new_start

    for line_content in hunk['lines']:
        # 确定行类型和内容
        if line_content.startswith('-'):
            line_type = 'removed'
            content = line_content[1:]
            display_old_line = old_line_no
            display_new_line = ''
            old_line_no += 1
        elif line_content.startswith('+'):
            line_type = 'added'
            content = line_content[1:]
            display_old_line = ''
            display_new_line = new_line_no
            new_line_no += 1
        else:
            line_type = 'context'
            content = line_content
            display_old_line = old_line_no
            display_new_line = new_line_no
            old_line_no += 1
            new_line_no += 1

        # 格式化行号显示
        line_number = display_new_line if display_new_line else display_old_line
        line_num_str = f"{line_number:4d}" if line_number else "    "

        # 根据行类型添加样式
        if line_type == 'removed':
            lines.extend([
                ('class:tool.patch.line_number.removed', line_num_str),
                ('class:tool.patch.diff.removed', f"- {content}")
            ])
        elif line_type == 'added':
            lines.extend([
                ('class:tool.patch.line_number.added', line_num_str),
                ('class:tool.patch.diff.added', f"+ {content}")
            ])
        else:  # context
            lines.extend([
                ('class:tool.patch.line_number', line_num_str),
                ('class:tool.patch.diff.context', f"  {content}")
            ])

    lines.append(('', "\n"))
    return lines


def format_bash_execute_tool_output(bash_execute_result: dict) -> FormattedText:
    """格式化展示Bash执行结果"""
    result = []
    stderr = bash_execute_result.get('stderr', '')
    error_message = bash_execute_result.get('error_message', '')
    stdout = bash_execute_result.get('stdout', '')

    if stderr and len(stderr.strip()) > 0:
        lines, remaining_lines = _format_multiline_text(stderr)
        result.append(("class:common.red", lines))
        if remaining_lines > 0:
            result.append(("class:common.gray", f"    ... +{remaining_lines} lines"))
    elif error_message and len(error_message.strip()) > 0:
        lines, remaining_lines = _format_multiline_text(error_message)
        result.append(("class:common.red", lines))
        if remaining_lines > 0:
            result.append(("class:common.gray", f"    ... +{remaining_lines} lines"))
    # 其次检查 stdout
    elif stdout and len(stdout.strip()) > 0:
        lines, remaining_lines = _format_multiline_text(stdout)
        result.append(("", lines))
        if remaining_lines > 0:
            result.append(("class:common.gray", f"    ... +{remaining_lines} lines"))
    else:
        # 如果都没有内容
        result.append(("class:common.gray", "  ⎿ (No content)"))

    return FormattedText(result)


def format_todo_list(todos: list[TodoItemStorage]) -> FormattedText:
    """格式化展示待办列表输出"""
    result = []

    if todos and len(todos) > 0:

        # 对todos排序
        def sort_key(item):
            status_order = {"completed": 0, "in_progress": 1, "pending": 2}
            priority_order = {"high": 0, "medium": 1, "low": 2}
            return (
                status_order.get(item.status, 3),
                item.create_at,
                priority_order.get(item.priority, 3),
            )

        todos.sort(key=sort_key)

        doing = next((todo.content for todo in todos if todo.status == 'in_progress'), None)
        if doing:
            result.append(("class:common.pink", f" * {doing}...\n"))
            first_pending = True
            for todo in todos:
                status = todo.status
                if status == "completed":
                    result.append(("class:common.gray", f"  ☒ {todo.content}\n"))
                elif status == "in_progress":
                    result.append(("bold", f"  ☐ {todo.content}\n"))
                elif status == "pending":
                    if first_pending:
                        result.append(("", f"  ☐ {todo.content}\n"))
                        first_pending = False
                    else:
                        result.append(("", f"  ☐ {todo.content}\n"))
    return FormattedText(result)


def _format_multiline_text(text, first_line_prefix="  ⎿ ", other_lines_prefix="    ", max_show_line=10):
    """格式化多行文本，为第一行和后续行添加不同前缀"""
    if not text:
        return ""

    lines = text.strip().split('\n')
    if not lines:
        return ""

    formatted_lines = []
    for i, line in enumerate(lines):
        if i == 0:  # 第一行
            formatted_lines.append(f"{first_line_prefix}{line}")
        else:  # 后续行
            formatted_lines.append(f"{other_lines_prefix}{line}")
    result_lines = formatted_lines[:max_show_line]
    remaining_line_count = len(lines) - max_show_line
    return '\n'.join(result_lines), remaining_line_count
