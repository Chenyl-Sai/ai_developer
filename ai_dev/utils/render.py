import json
import time

from prompt_toolkit.formatted_text import FormattedText, AnyFormattedText, HTML, merge_formatted_text
from typing import Any, TypedDict, Union
from pydantic import BaseModel
from async_lru import alru_cache

from ai_dev.constants.product import PRODUCT_NAME
from ai_dev.core.global_state import GlobalState
from ai_dev.utils.file import get_absolute_path
from ai_dev.utils.todo import TodoItemStorage
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
    tool_args: dict[str, Any] | None
    status: str | None = None
    message: str | None = None
    exec_result_details: Any | None = None
    context: dict | None = None

class TaskBlock(BaseModel):
    id: str
    tool_name: str
    tool_args: dict[str, Any] | None
    task_id: str | None = None # 用于定位子任务输出所属的父节点
    status: str | None = None
    message: str | None = None # 总结性消息，共调用了多少工具、耗时、token消耗等等
    process_blocks: list = [] # 子任务内部各种工具调用、消息输出模块
    process_block_dict: dict[str, Any] | None = {} # 按消息/工具id组织的块
    task_response: str | None = None # 子任务最终响应输出
    # 统计信息
    start_time: float | None = None
    end_time: float | None = None
    tool_ids: set[str] | None = set()

OutputBlock = Union[str, tuple[str, str], InputBlock, MessageBlock, ToolBlock, TaskBlock]


@alru_cache(maxsize=100)
async def format_ai_output(text, prefix_space_count:int=2):
    """将Markdown文本转换为ANSI格式用于终端显示
    
    Args:
        text (str): Markdown格式文本
        prefix_space_count (int): 新换行前面要添加的空格的数量(为了文本对齐)
        
    Returns:
        ANSI: prompt_toolkit的ANSI格式对象
    """
    if not text or not text.strip():
        from prompt_toolkit.formatted_text import ANSI
        return ANSI(" ")
    
    from rich.console import Console
    from rich.markdown import Markdown
    from io import StringIO
    from prompt_toolkit.formatted_text import ANSI

    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, color_system="truecolor")
    text = text.replace("\n",f"{' ' * prefix_space_count}\n")
    console.print(Markdown(text))
    ansi_text = buffer.getvalue()
    return ANSI(ansi_text)


async def format_output_block(block: OutputBlock, breathe_color_controller: dict) -> AnyFormattedText:
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
        formatted_content = await format_ai_output(block.content)
        return merge_formatted_text([prefix, formatted_content])
    # 工具执行
    elif isinstance(block, ToolBlock):
        return await format_tool_block(block)
    elif isinstance(block, TaskBlock):
        return await format_task_tool_block(block, breathe_color_controller)


async def format_tool_block(block: ToolBlock, is_sub_agent_tool: bool=False) -> AnyFormattedText:
    tool_status = block.status
    # 工具开始执行 & 执行过程中
    html_text = None
    if tool_status == "start":
        # 展示标题
        html_text = f"  ⎿  <bold>{_format_show_tool_name(block)}</bold>" if is_sub_agent_tool \
            else f"<style fg='#000000'>⏺</style> <bold>{_format_show_tool_name(block)}</bold>"
        if block.tool_args:
            escaped_message = _smart_escape_html(_format_show_tool_args(block))
            html_text += f"({escaped_message})"
        html_text += " \n"
        # 展示过程中的额外消息
        if block.message:
            # 智能转义：只转义非HTML标签的内容
            escaped_message = _smart_escape_html(block.message)
            html_text += f"{'     ' if is_sub_agent_tool else '  ⎿  '}{escaped_message}"
        else:
            html_text += f"{'     ' if is_sub_agent_tool else '  ⎿  '}Doing…"
        return _safe_html_render(html_text, block)
    # 工具执行成功
    elif tool_status == "success":
        # 展示标题，图标变色
        html_text = f"  ⎿  <bold>{_format_show_tool_name(block)}</bold>" if is_sub_agent_tool \
            else f"<style fg='#33ff66'>⏺</style> <bold>{_format_show_tool_name(block)}</bold>"
        if block.tool_args:
            escaped_message = _smart_escape_html(_format_show_tool_args(block))
            html_text += f"({escaped_message})"
        html_text += " \n"
        # 展示总结性的信息
        summary = _format_show_tool_summary(block)
        if summary:
            # 智能转义：只转义非HTML标签的内容
            escaped_message = _smart_escape_html(summary)
            html_text += f"{'     ' if is_sub_agent_tool else '  ⎿  '}{escaped_message}"
        html_text += " \n"
        html = _safe_html_render(html_text, block)
        # 对于一些特殊的工具需要展示执行的详情
        detail = await format_tool_exec_detail(block)
        if detail:
            return merge_formatted_text([html, detail])
        else:
            return html
    # 工具执行失败
    elif tool_status == "error":
        # 展示标题，图标变色
        html_text = f"  ⎿  <bold>{_format_show_tool_name(block)}</bold>" if is_sub_agent_tool \
            else f"<style fg='#ff0000'>⏺</style> <bold>{_format_show_tool_name(block)}</bold>"
        if block.tool_args:
            escaped_message = _smart_escape_html(_format_show_tool_args(block))
            html_text += f"({escaped_message})"
        html_text += " \n"
        # 展示总结性的信息
        if block.message:
            # 智能转义：只转义非HTML标签的内容
            escaped_message = _smart_escape_html(block.message)
            html_text += f"{'     ' if is_sub_agent_tool else '  ⎿  '}<style fg='#ff0000'>{escaped_message}</style>"
        else:
            html_text += f"{'     ' if is_sub_agent_tool else '  ⎿  '}<style fg='#ff0000'>Error</style>"
        html_text += " \n"
        html = _safe_html_render(html_text, block)
        # 对于一些特殊的工具需要展示执行的详情
        detail = await format_tool_exec_detail(block)
        if detail:
            return merge_formatted_text([html, detail])
        else:
            return html

async def format_task_tool_block(block: TaskBlock, breathe_color_controller: dict) -> AnyFormattedText:
    formatted_blocks = []
    color = '#DDDDDD'
    if block.status == 'start':
        if breathe_color_controller and breathe_color_controller.get(block.id) == 0:
            color = '#FFFFFF'
        else:
            color = '#DDDDDD'
    elif block.status == 'success':
        color = '#33FF66'
    elif block.status == 'error':
        color = '#FF0000'
    # 展示标题及prompt块
    html_text = f"<style fg='{color}'>⏺</style> <bold>Task({block.task_id})</bold>"
    if block.tool_args:
        escaped_message = _smart_escape_html(block.tool_args.get("description"))
        html_text += f"({escaped_message})"
    html_text += f"(<style fg='#DDDDDD'>ctrl+o to {'hide' if GlobalState.get_show_output_details() else 'show'} details</style>)"
    html_text += " \n"
    # if block.status == 'start':
    # 展示prompt
    prompt = block.tool_args.get("prompt")
    if prompt and GlobalState.get_show_output_details():
        prompt = "Prompt:" + prompt
        for line in prompt.split("\n"):
            escaped_message = _smart_escape_html(line)
            html_text += f"    {escaped_message}\n"
    formatted_blocks.append(_safe_html_render(html_text, block))
    # 内部工具及消息列表块
    if block.process_blocks:
        if GlobalState.get_show_output_details():
            for sub_block in block.process_blocks:
                if isinstance(sub_block, MessageBlock):
                    formatted_blocks.append(await format_ai_output(sub_block.content, 4))
                elif isinstance(sub_block, ToolBlock):
                    formatted_blocks.append(await format_tool_block(sub_block, True))
        elif block.status == 'start':
            last_block = block.process_blocks[-1]
            if isinstance(last_block, MessageBlock):
                formatted_blocks.append(await format_ai_output(last_block.content, 4))
            elif isinstance(last_block, ToolBlock):
                formatted_blocks.append(await format_tool_block(last_block, True))

    # 最终agent结果
    if block.task_response and GlobalState.get_show_output_details():
        formatted_blocks.append(_safe_html_render(f"  ⎿  <style fg='#33ff66'>Agent Response:</style>\n", block))
        formatted_blocks.append(await format_ai_output(block.task_response, 4))

    if block.status == 'success':
        if block.start_time is None:
            block.start_time = time.time()
        if block.end_time is None:
            block.end_time = time.time()
        time_cost = block.end_time - block.start_time
        tool_count = len(block.tool_ids)
        formatted_blocks.append(_safe_html_render(f"  ⎿  Done ({tool_count} tool uses · {format_time_cost(time_cost)})", block))
    elif block.status == 'error':
        formatted_blocks.append(_safe_html_render(f"  ⎿  <style fg='#FF6B6B'>{block.message}</style>", block))
    return merge_formatted_text(formatted_blocks)

def format_time_cost(seconds: float) -> str:
    if seconds <= 0:
        seconds = 0
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s or not parts:  # 确保至少有一个部分
        parts.append(f"{s}s")

    return " ".join(parts)

async def format_tool_exec_detail(block: ToolBlock) -> AnyFormattedText:
    tool_name = block.tool_name
    # 文件编辑 & 文件写入， 需要展示修改对比
    if tool_name in ["FileEditTool", "FileWriteTool"]:
        if block.exec_result_details:
            patch = json.loads(block.exec_result_details).get("patch")
            if patch:
                return FormattedText(render_hunks(patch))
    # Bash命令执行
    elif tool_name in ["BashExecuteTool"]:
        return format_bash_execute_tool_output(json.loads(block.exec_result_details))

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

    lines.append(('', " \n"))
    return lines


def format_bash_execute_tool_output(bash_execute_result: dict) -> FormattedText:
    """格式化展示Bash执行结果"""
    result = []
    if bash_execute_result:
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


def _smart_escape_html(text: str) -> str:
    """智能转义HTML：只转义非HTML标签的内容
    
    保留合法的HTML标签（如<bold>, <style>等），只转义其他内容中的特殊字符
    """
    if not text:
        return ""
    
    import re
    
    # 定义合法的HTML标签模式
    html_tag_pattern = r'<(/?)(style|bold|italic|underline|ansired|ansigreen|ansiyellow|ansiblue|ansimagenta|ansicyan|ansigray|ansibrightred|ansibrightgreen|ansibrightyellow|ansibrightblue|ansibrightmagenta|ansibrightcyan|ansibrightwhite|fg|bg|b)[^>]*>'
    
    # 将文本分割为HTML标签和非标签部分
    parts = []
    last_end = 0
    
    for match in re.finditer(html_tag_pattern, text):
        # 添加标签前的普通文本
        if match.start() > last_end:
            plain_text = text[last_end:match.start()]
            # 转义普通文本中的特殊字符
            escaped_text = plain_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            parts.append(escaped_text)
        
        # 添加HTML标签（不转义）
        parts.append(match.group(0))
        last_end = match.end()
    
    # 添加剩余的普通文本
    if last_end < len(text):
        plain_text = text[last_end:]
        escaped_text = plain_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        parts.append(escaped_text)
    
    return ''.join(parts)


def _safe_html_render(html_text: str, block: ToolBlock | TaskBlock) -> AnyFormattedText:
    """安全的HTML渲染，包含错误处理和实时反馈"""
    try:
        return HTML(html_text)
    except Exception as e:
        # 记录详细错误信息
        error_msg = f"HTML渲染错误: {str(e)}"
        agent_logger.error(f"Failed to render tool block {block.tool_name}: {e}")
        agent_logger.debug(f"Problematic HTML: {html_text}")
        
        # 返回包含错误信息的格式化文本
        return FormattedText([
            ("class:common.red", f"⏺ {block.tool_name}"),
            ("", " \n"),
            ("class:common.red", f"  ⎿ 渲染错误: {str(e)}"),
            ("", " \n")
        ])


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



def format_permission_choice(request_info: dict) -> tuple[FormattedText, list]:
    """格式化权限选择界面 - 适配多种权限类型"""
    display_type = request_info.get("display_type", "generic")

    if display_type == "file_write":
        return _format_file_write_request(request_info)
    elif display_type == "file_edit":
        return _format_file_edit_request(request_info)
    elif display_type == "bash_execute":
        return _format_bash_execute_request(request_info)
    else:
        return _format_generic_request(request_info)

def _format_file_write_request(request_info: dict) -> tuple[FormattedText, list]:
    """格式化文件写入权限请求"""
    file_path = request_info.get("file_path", "")
    file_name = request_info.get("file_name", "")
    patch_info = request_info.get("patch_info", {})

    hunks = patch_info.get("hunks", [])
    result = []
    result.append(("class:permission.title", f" Create File({file_path})\n\n"))
    result.extend(render_hunks(hunks))
    result.append(("", " \n \n"))
    result.append(("", f" Do you want to create {file_name}?\n"))
    options = [
        "1. Yes",
        "2. Yes, allow all edits during this session",
        f"3. No, and tell {PRODUCT_NAME} what to do differently",
    ]

    return FormattedText(result), options

def _format_file_edit_request(request_info: dict) -> tuple[FormattedText, list]:
    """格式化文件编辑权限请求"""
    file_path = request_info.get("file_path", "")
    file_name = request_info.get("file_name", "")
    patch_info = request_info.get("patch_info", {})

    hunks = patch_info.get("hunks", [])
    result = []
    result.append(("class:permission.title", f" Edit File({file_path})\n\n"))
    result.extend(render_hunks(hunks))
    result.append(("", " \n \n"))
    result.append(("", f" Do you want to make this edit to {file_name}?\n"))

    options = [
        "1. Yes",
        "2. Yes, allow all edits during this session",
        f"3. No, and tell {PRODUCT_NAME} what to do differently",
    ]

    return FormattedText(result), options

def _format_bash_execute_request(request_info: dict) -> tuple[FormattedText, list]:
    """格式化Bash命令执行权限请求"""
    command = request_info.get("command", "")
    propose = request_info.get("propose", "")

    command_type = command
    command_parts = command.strip().split()
    if command_parts:
        command_type = command_parts[0]

    result = []
    result.append(("class:permission.title", f" Bash command\n\n"))
    result.append(("", f"   {command}\n"))
    result.append(("class:common.gray", f"   {propose}"))
    result.append(("", " \n \n"))
    result.append(("", f" Do you want to proceed\n"))
    options = [
        "1. Yes",
        f"2. Yes, and don't ask again for {command_type} commands in {GlobalState.get_working_directory()}",
        f"3. No, and tell {PRODUCT_NAME} what to do differently",
    ]
    return FormattedText(result), options

def _format_generic_request(request_info: dict) -> tuple[FormattedText, list]:
    """格式化通用权限请求"""
    tool_name = request_info.get('tool_name')
    tool_args = request_info.get("tool_args", {})
    text = ""
    if tool_args:
        for key, value in tool_args.items():
            text += f" {key} : {value}\n"

    result = []
    result.append(("class:permission.title", f" Execute tool\n\n"))
    result.append(("", f"   Tool name: {tool_name}\n"))
    result.append(("", f"   Tool args: {text}"))
    result.append(("", " \n \n"))
    result.append(("", f" Do you want to proceed\n"))
    options = [
        "1. Yes",
        f"2. Yes, and don't ask again for {tool_name} tool during this session",
        f"3. No, and tell {PRODUCT_NAME} what to do differently",
    ]
    return FormattedText(result), options

def _format_show_tool_name(block: ToolBlock) -> str:
    tool_name = block.tool_name
    if tool_name == "BashExecuteTool":
        return "Bash"
    elif tool_name == "FileEditTool":
        return "Edit"
    elif tool_name == "FileListTool":
        return "List"
    elif tool_name == "FileReadTool":
        return "Read"
    elif tool_name == "FileWriteTool":
        return "Write"
    elif tool_name in ["GlobTool", "GrepTool"]:
        return "Search"
    else:
        return tool_name

def _format_show_tool_args(block: ToolBlock) -> str:
    tool_name = block.tool_name
    if tool_name == "BashExecuteTool":
        command = block.tool_args.get("command")
        MAX_SHOW_LINES = 3
        MAX_CHARS_PER_LINE = 200
        if not command:
            return ""

        # 按换行符分割字符串
        lines = command.split('\n')
        truncated_lines = lines[:MAX_SHOW_LINES]

        # 对每一行进行字符数截取
        result_lines = []
        for line in truncated_lines:
            # 如果行长度超过限制，则截取并在末尾添加省略号
            if len(line) > MAX_CHARS_PER_LINE:
                truncated_line = line[:MAX_CHARS_PER_LINE] + "..."
            else:
                truncated_line = line
            result_lines.append(truncated_line)

        # 如果原始行数超过最大行数，在最后添加省略号表示还有更多内容
        if len(lines) > MAX_SHOW_LINES:
            result_lines.append("...")

        # 用换行符连接所有行
        return '\n'.join(result_lines)
    elif tool_name in ["FileEditTool", "FileReadTool", "FileWriteTool"]:
        safe_path = get_absolute_path(block.tool_args.get("file_path"))
        relative_path = str(safe_path.relative_to(GlobalState.get_working_directory()))
        return f"{relative_path}"
    elif tool_name == "FileListTool":
        return block.tool_args.get("path")
    else:
        text = ""
        if block.tool_args:
            for key, value in block.tool_args.items():
                if key not in ["context"]:
                    text += f" {key} : {value}\n"
        return text

def _format_show_tool_summary(block: ToolBlock) -> str:
    tool_name = block.tool_name
    if tool_name == "FileEditTool":
        edit_result = json.loads(block.exec_result_details)
        hunks = edit_result.get("patch")
        total_add = 0
        total_remove = 0
        for hunk in hunks if hunks else []:
            for line in hunk["lines"]:
                if line.startswith('-'):
                    total_remove += 1
                elif line.startswith('+'):
                    total_add += 1

        return f"Updated {edit_result.get('file_path')} with {total_add} additions and {total_remove} removal"
    elif tool_name in ["FileListTool", "GlobTool", "GrepTool"]:
        return f"Found <b>{block.exec_result_details.get('found_file_count', 0)}</b> files"
    elif tool_name == "FileReadTool":
        result_for_show = json.loads(block.exec_result_details)
        """生成文件读取的成功消息"""
        line_count = result_for_show.get("line_count", 0)
        total_lines = result_for_show.get("total_lines", 0)
        start_line = result_for_show.get("start_line", 1)

        if line_count == total_lines:
            return f"Read <b>{line_count}</b> lines"
        else:
            end_line = start_line + line_count - 1
            return f"Read <b>{line_count}</b> lines (lines {start_line}-{end_line} of {total_lines})"
    elif tool_name == "FileWriteTool":
        result_for_show = json.loads(block.exec_result_details)
        hunks = result_for_show.get("patch")
        total_add = 0
        for hunk in hunks if hunks else []:
            total_add += len(hunk["lines"])

        return f"Wrote <bold>{total_add}</bold> lines to <bold>{result_for_show.get('file_path')}</bold>"
    else:
        return ""

