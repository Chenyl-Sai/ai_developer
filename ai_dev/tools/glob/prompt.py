from .constant import MAX_FILES

prompt = """- Fast file pattern matching tool that works with any codebase size
- Supports glob patterns like "**/*.js" or "src/**/*.ts"
- Returns matching file paths sorted by modification time
- Use this tool when you need to find files by name patterns
- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead"""

prompt_too_many_files = f"""There are more than {MAX_FILES} files in the repository. Use the LS tool (passing a specific path), BashExecuteTool tool, and other tools to explore nested directories.   
The first {MAX_FILES} files and directories are included below:\n\n"""