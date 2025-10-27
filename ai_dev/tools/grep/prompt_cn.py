from .constant import MAX_FILES

prompt = """- 快速的内容搜索工具，适用于任意大小的代码库
- 使用正则表达式搜索文件内容
- 支持完整的正则语法（例如 `log.*Error`、`function\s+\w+` 等）
- 可通过 include 参数 按模式筛选文件（例如 `*.js`、`*.{ts,tsx}`）
- 返回按修改时间排序的匹配文件路径
- 当需要查找包含特定模式的文件时，使用此工具
- 如果进行的是开放式搜索，可能需要多轮 glob 和 grep 操作，请改用 TaskTool 工具"""

prompt_too_many_files = f"""仓库中有超过 {MAX_FILES} 个文件。请使用 `FileListTool` 工具（指定具体路径）、`BashExecuteTool` 工具及其他工具来探索嵌套目录。  
下面仅列出了前 {MAX_FILES} 个文件和目录：\n\n"""