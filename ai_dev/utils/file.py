import chardet
from pathlib import Path

from ai_dev.core.global_state import GlobalState
from ai_dev.utils.logger import agent_logger

def detect_file_encoding(file_path: str) -> str:
    """
    检测文件编码，默认回退 utf-8
    """
    with open(file_path, "rb") as f:
        raw = f.read(4096)  # 只读一部分就够了
    result = chardet.detect(raw)
    encoding = result.get("encoding")
    return encoding if encoding else "utf-8"


def detect_line_endings_direct(file_path: str, encoding: str = "utf-8") -> str:
    """
    精确检测文件的行尾符，返回 'CRLF' 或 'LF'
    仿照 JS detectLineEndingsDirect 的逻辑。
    """
    try:
        with open(file_path, "rb") as f:
            raw = f.read(4096)

        # 解码（忽略错误，避免非文本导致异常）
        content = raw.decode(encoding, errors="ignore")

        crlf_count = 0
        lf_count = 0

        for i, ch in enumerate(content):
            if ch == "\n":
                if i > 0 and content[i - 1] == "\r":
                    crlf_count += 1
                else:
                    lf_count += 1

        return "CRLF" if crlf_count > lf_count else "LF"

    except Exception as e:
        agent_logger.error(f"Error detecting line endings for file {file_path}", exception=e)
        return "LF"

def write_text_content(file_path: str, content: str, encoding: str, endings: str):
    # 注意 line endings 转换
    if endings == "CRLF":
        content = content.replace("\n", "\r\n")
    with open(file_path, "w", encoding=encoding, newline="") as f:
        f.write(content)

def get_absolute_path(*paths) -> Path:
    from ai_dev.core.global_state import GlobalState
    """安全地拼接路径"""
    if paths:
        first_path = Path(paths[0])
        # 如果第一个路径是绝对路径，直接使用
        if first_path.is_absolute():
            joined = first_path.resolve()
            # 如果有多个路径，拼接剩余部分
            if len(paths) > 1:
                joined = joined.joinpath(*paths[1:]).resolve()
        else:
            # 如果是相对路径，拼接工作目录
            joined = Path(GlobalState.get_working_directory()).joinpath(*paths).resolve()
    else:
        joined = Path(GlobalState.get_working_directory()).resolve()

    return joined

def get_relative_path(path) -> Path:
    absolute_path = get_absolute_path(path)
    return absolute_path.relative_to(GlobalState.get_working_directory())
