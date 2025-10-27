from .constant import MAX_FILES

prompt = """- 快速的文件模式匹配工具，适用于任意大小的代码库
- 支持类似 "**/*.js" 或 "src/**/*.ts" 的 glob 模式
- 返回按修改时间排序的匹配文件路径
- 当需要根据文件名模式查找文件时，使用此工具
- 如果进行的是开放式搜索，可能需要多轮 glob 和 grep 操作，请改用 TaskTool 工具"""

prompt_too_many_files = f"""仓库中有超过 {MAX_FILES} 个文件。请使用 `FileListTool` 工具（指定具体路径）、`BashExecuteTool` 工具及其他工具来探索嵌套目录。  
下面仅列出了前 {MAX_FILES} 个文件和目录：\n\n"""