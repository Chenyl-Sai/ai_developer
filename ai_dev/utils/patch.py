import difflib

CONTEXT_LINES = 3

AMPERSAND_TOKEN = "<<:AMPERSAND_TOKEN:>>"
DOLLAR_TOKEN = "<<:DOLLAR_TOKEN:>>"


def _tokenize(text: str) -> str:
    return text.replace("&", AMPERSAND_TOKEN).replace("$", DOLLAR_TOKEN)


def _detokenize(text: str) -> str:
    return text.replace(AMPERSAND_TOKEN, "&").replace(DOLLAR_TOKEN, "$")


def get_patch(file_path: str, file_contents: str, old_str: str, new_str: str):
    """
    生成结构化的 diff patch，返回类似 JS 里的 hunks 结构。
    """

    # 替换 token，避免 diff 出错
    file_contents_token = _tokenize(file_contents)
    old_str_token = _tokenize(old_str)
    new_str_token = _tokenize(new_str)

    # 构造新内容（替换 old_str -> new_str）
    new_contents_token = file_contents_token.replace(old_str_token, new_str_token)

    # 拆分为行
    old_lines = file_contents_token.splitlines(keepends=True)
    new_lines = new_contents_token.splitlines(keepends=True)

    # 生成 unified diff
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=file_path,
            tofile=file_path,
            n=CONTEXT_LINES,
            lineterm=""
        )
    )

    # 解析 diff 成 hunks
    hunks = []
    hunk = None

    for line in diff_lines:
        if line.startswith("@@"):
            # 开始一个新的 hunk
            if hunk:
                hunks.append(hunk)
            hunk = {"header": line, "lines": []}
        elif hunk is not None:
            hunk["lines"].append(line)

    if hunk:
        hunks.append(hunk)

    # 替换 token 回原字符
    for h in hunks:
        h["lines"] = [_detokenize(l) for l in h["lines"]]

    return hunks

