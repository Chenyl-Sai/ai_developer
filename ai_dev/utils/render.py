from prompt_toolkit.formatted_text import FormattedText

import ast


async def render_tool_result(chunk: dict) -> list[tuple[str, str]]:
    """渲染工具执行结果

    Args:
        chunk (dict): 流式输出的工具执行结果消息，包含tool_name、message、status、result、error

    Returns:
        list[tuples[str, str]]: 多行渲染文本，每一行是一个tuple，包含两个元素(kind, message)
    """
    result = []
    message = chunk.get("message")
    status = chunk.get("status")
    if status == "error":
        error = chunk.get("error")
        result.append(("tool_error", f"    <style color='red'>{error if error else message}</style>"))
    else:
        if message is not None and len(message) > 0:
            result.append(("tool_result", f"{message}"))
        if chunk.get("tool_name") in ["FileEditTool", "FileWriteTool"]:
            result.append(("tool_patch", str({
                "file_path": chunk.get("result").get("absolute_path"),
                "hunks": chunk.get("result").get("patch"),
            })))
        elif chunk.get("tool_name") in ["BashExecuteTool"]:
            result.append(("base_execute_result", str(chunk.get("result"))))

        result.append(("", ""))

    return result


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


def format_patch_output(text) -> FormattedText:
    patch_info = ast.literal_eval(text)
    hunks = patch_info.get("hunks")
    return FormattedText(render_hunks(hunks))


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


def format_base_execute_tool_output(str) -> FormattedText:
    result = []

    bash_execute_result = ast.literal_eval(str)

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
