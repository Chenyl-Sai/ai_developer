from .constant import MAX_LINES_TO_READ, MAX_LINE_LENGTH

prompt = f"""从本地文件系统中读取一个文件。  
参数 `file_path` 必须是**绝对路径**（不能是相对路径）。  
默认情况下，该工具会从文件开头开始读取最多 {MAX_LINES_TO_READ} 行。  
你也可以选择性地指定读取偏移量（`offset`）和行数限制（`limit`）——这在读取长文件时特别有用。  
但通常建议不设置这些参数，以便读取整个文件。  
任何超过 {MAX_LINE_LENGTH} 个字符的行都会被截断。  
对于图像文件，工具会直接显示图像内容。"""
