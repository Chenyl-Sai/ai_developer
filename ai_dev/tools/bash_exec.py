"""
Bash 执行工具 - 支持异步执行、回调机制和命令队列
"""

import asyncio
import subprocess
from typing import Any, Dict, Optional, Callable, Type, Generator
from pydantic import BaseModel, Field
from .base import StreamTool, CommonToolArgs
from ai_dev.utils.bash_executor import (
    BashExecutor,
    CommandResult,
    CommandStatus,
    get_bash_executor
)
from ..core.global_state import GlobalState

MAX_OUTPUT_LENGTH = 30000
BANNED_COMMANDS = [
  'alias',
  'curl',
  'curlie',
  'wget',
  'axel',
  'aria2c',
  'nc',
  'telnet',
  'lynx',
  'w3m',
  'links',
  'httpie',
  'xh',
  'http-prompt',
  'chrome',
  'firefox',
  'safari',
]

class BashExecuteArgs(CommonToolArgs):
    """Bash 执行工具参数"""
    command: str = Field(..., description="The command to execute")
    propose: str = Field(description="Briefly explain the intention of the bash script executed this time")
    timeout: Optional[int] = Field(default=None, description="Optional timeout in seconds (max 600)")

class BashExecuteTool(StreamTool):
    """Bash 执行工具"""

    name: str = "BashExecuteTool"
    description: str = f"""Executes a given bash command in a persistent shell session with optional timeout, ensuring proper handling and security measures.

Before executing the command, please follow these steps:

1. Directory Verification:
   - If the command will create new directories or files, first use the LS tool to verify the parent directory exists and is the correct location
   - For example, before running "mkdir foo/bar", first use LS to check that "foo" exists and is the intended parent directory

2. Security Check:
   - For security and to limit the threat of a prompt injection attack, some commands are limited or banned. If you use a disallowed command, you will receive an error message explaining the restriction. Explain the error to the User.
   - Verify that the command is not one of the banned commands: {", ".join(BANNED_COMMANDS)}.

3. Command Execution:
   - After ensuring proper quoting, execute the command.
   - Capture the output of the command.

4. Output Processing:
   - If the output exceeds {MAX_OUTPUT_LENGTH} characters, output will be truncated before being returned to you.
   - Prepare the output for display to the user.

5. Return Result:
   - Provide the processed output of the command.
   - If any errors occurred during execution, include those in the output.

Usage notes:
  - The command argument is required.
  - You can specify an optional timeout in milliseconds (up to 600000ms / 10 minutes). If not specified, commands will timeout after 30 minutes.
  - VERY IMPORTANT: You MUST avoid using search commands like \`find\` and \`grep\`. Instead use GrepTool, GlobTool, or TaskTool to search. You MUST avoid read tools like \`cat\`, \`head\`, \`tail\`, and \`ls\`, and use FileReadTool and FileListTool to read files.
  - When issuing multiple commands, use the ';' or '&&' operator to separate them. DO NOT use newlines (newlines are ok in quoted strings).
  - IMPORTANT: All commands share the same shell session. Shell state (environment variables, virtual environments, current directory, etc.) persist between commands. For example, if you set an environment variable as part of a command, the environment variable will persist for subsequent commands.
  - Try to maintain your current working directory throughout the session by using absolute paths and avoiding usage of \`cd\`. You may use \`cd\` if the User explicitly requests it.
  <good-example>
  pytest /foo/bar/tests
  </good-example>
  <bad-example>
  cd /foo/bar && pytest tests
  </bad-example>

# Committing changes with git

When the user asks you to create a new git commit, follow these steps carefully:

1. Start with a single message that contains exactly three tool_use blocks that do the following (it is VERY IMPORTANT that you send these tool_use blocks in a single message, otherwise it will feel slow to the user!):
   - Run a git status command to see all untracked files.
   - Run a git diff command to see both staged and unstaged changes that will be committed.
   - Run a git log command to see recent commit messages, so that you can follow this repository's commit message style.

2. Use the git context at the start of this conversation to determine which files are relevant to your commit. Add relevant untracked files to the staging area. Do not commit files that were already modified at the start of this conversation, if they are not relevant to your commit.

3. Analyze all staged changes (both previously staged and newly added) and draft a commit message. Wrap your analysis process in <commit_analysis> tags:

<commit_analysis>
- List the files that have been changed or added
- Summarize the nature of the changes (eg. new feature, enhancement to an existing feature, bug fix, refactoring, test, docs, etc.)
- Brainstorm the purpose or motivation behind these changes
- Do not use tools to explore code, beyond what is available in the git context
- Assess the impact of these changes on the overall project
- Check for any sensitive information that shouldn't be committed
- Draft a concise (1-2 sentences) commit message that focuses on the "why" rather than the "what"
- Ensure your language is clear, concise, and to the point
- Ensure the message accurately reflects the changes and their purpose (i.e. "add" means a wholly new feature, "update" means an enhancement to an existing feature, "fix" means a bug fix, etc.)
- Ensure the message is not generic (avoid words like "Update" or "Fix" without context)
- Review the draft message to ensure it accurately reflects the changes and their purpose
</commit_analysis>

4. Create the commit with a message ending with:
🤖 Generated with PRODUCT_NAME & MODEL_NAME

- In order to ensure good formatting, ALWAYS pass the commit message via a HEREDOC, a la this example:
<example>
git commit -m "$(cat <<'EOF'
   Commit message here.

   🤖 Generated with PRODUCT_NAME & MODEL_NAME
   EOF
   )"
</example>

5. If the commit fails due to pre-commit hook changes, retry the commit ONCE to include these automated changes. If it fails again, it usually means a pre-commit hook is preventing the commit. If the commit succeeds but you notice that files were modified by the pre-commit hook, you MUST amend your commit to include them.

6. Finally, run git status to make sure the commit succeeded.

Important notes:
- When possible, combine the "git add" and "git commit" commands into a single "git commit -am" command, to speed things up
- However, be careful not to stage files (e.g. with \`git add .\`) for commits that aren't part of the change, they may have untracked files they want to keep around, but not commit.
- NEVER update the git config
- DO NOT push to the remote repository
- IMPORTANT: Never use git commands with the -i flag (like git rebase -i or git add -i) since they require interactive input which is not supported.
- If there are no changes to commit (i.e., no untracked files and no modifications), do not create an empty commit
- Ensure your commit message is meaningful and concise. It should explain the purpose of the changes, not just describe them.
- Return an empty response - the user will see the git output directly

# Creating pull requests
Use the gh command via the Bash tool for ALL GitHub-related tasks including working with issues, pull requests, checks, and releases. If given a Github URL use the gh command to get the information needed.

IMPORTANT: When the user asks you to create a pull request, follow these steps carefully:

1. Understand the current state of the branch. Remember to send a single message that contains multiple tool_use blocks (it is VERY IMPORTANT that you do this in a single message, otherwise it will feel slow to the user!):
   - Run a git status command to see all untracked files.
   - Run a git diff command to see both staged and unstaged changes that will be committed.
   - Check if the current branch tracks a remote branch and is up to date with the remote, so you know if you need to push to the remote
   - Run a git log command and \`git diff main...HEAD\` to understand the full commit history for the current branch (from the time it diverged from the \`main\` branch.)

2. Create new branch if needed

3. Commit changes if needed

4. Push to remote with -u flag if needed

5. Analyze all changes that will be included in the pull request, making sure to look at all relevant commits (not just the latest commit, but all commits that will be included in the pull request!), and draft a pull request summary. Wrap your analysis process in <pr_analysis> tags:

<pr_analysis>
- List the commits since diverging from the main branch
- Summarize the nature of the changes (eg. new feature, enhancement to an existing feature, bug fix, refactoring, test, docs, etc.)
- Brainstorm the purpose or motivation behind these changes
- Assess the impact of these changes on the overall project
- Do not use tools to explore code, beyond what is available in the git context
- Check for any sensitive information that shouldn't be committed
- Draft a concise (1-2 bullet points) pull request summary that focuses on the "why" rather than the "what"
- Ensure the summary accurately reflects all changes since diverging from the main branch
- Ensure your language is clear, concise, and to the point
- Ensure the summary accurately reflects the changes and their purpose (ie. "add" means a wholly new feature, "update" means an enhancement to an existing feature, "fix" means a bug fix, etc.)
- Ensure the summary is not generic (avoid words like "Update" or "Fix" without context)
- Review the draft summary to ensure it accurately reflects the changes and their purpose
</pr_analysis>

Important:
- Return an empty response - the user will see the gh output directly
- Never update git config"""
    args_schema: Type[BaseModel] = BashExecuteArgs

    # 全局执行器实例
    _executor: Optional[BashExecutor] = None

    @property
    def show_name(self) -> str:
        return "Bash"

    @property
    def executor(self) -> BashExecutor:
        """获取执行器实例"""
        if self._executor is None:
            self._executor = BashExecutor()
            self._executor.start_queue_processor()
        return self._executor

    def _execute_tool(self, **kwargs) -> Generator[Dict[str, Any], None, None]:
        """执行工具逻辑 - 同步等待命令完成并返回结果"""
        args = BashExecuteArgs(**kwargs)

        # 验证工作目录
        working_dir = GlobalState.get_working_directory()

        # 都直接执行
        use_queue = False
        if use_queue:
            # 对于队列执行，使用队列处理器
            result_data = self._execute_with_queue(args, working_dir)
        else:
            # 对于直接执行，直接运行命令
            result_data = self._execute_direct(args, working_dir)

        yield {
            "type": "tool_end",
            "result_for_llm": result_data,
        }

    def _execute_direct(self, args: BashExecuteArgs, working_dir: str) -> Dict[str, Any]:
        """直接执行命令"""
        try:
            import time
            start_time = time.time()

            # 直接执行命令
            result = self._run_command_sync(
                args.command,
                working_dir,
                args.timeout
            )

            execution_time = time.time() - start_time
            command_result = CommandResult(
                command_id="direct_exec",
                command=args.command,
                status=CommandStatus.COMPLETED,
                return_code=result["return_code"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                execution_time=execution_time
            )

            return self._format_command_result(command_result)

        except Exception as e:
            return {
                "status": "failed",
                "return_code": -1,
                "stdout": "",
                "stderr": "",
                "execution_time": 0.0,
                "error_message": f"命令执行失败: {str(e)}"
            }

    def _run_command_sync(self, command: str, working_directory: str, timeout: Optional[int]) -> Dict[str, Any]:
        """同步执行命令"""
        try:
            process = subprocess.run(
                command,
                shell=True,
                cwd=working_directory,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            return {
                "return_code": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr
            }

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Command timed out after {timeout} seconds")
        except Exception as e:
            raise RuntimeError(f"Command execution failed: {e}")

    def _execute_with_queue(self, args: BashExecuteArgs, working_dir: str) -> Dict[str, Any]:
        """使用队列执行命令"""
        import threading
        result_event = threading.Event()
        result_data: dict[str, Optional[CommandResult]] = {"result": None}

        def callback_wrapper(command_result: CommandResult):
            """包装回调函数，存储结果并通知主线程"""
            result_data["result"] = command_result
            result_event.set()

        # 将命令加入队列
        command_id = asyncio.run(
            self.executor.queue_command(
                command=args.command,
                working_directory=working_dir,
                timeout=args.timeout,
                callback=callback_wrapper
            )
        )

        # 等待命令完成（最多等待timeout + 5秒）
        max_wait_time = (args.timeout or 30) + 5
        if result_event.wait(timeout=max_wait_time):
            command_result = result_data["result"]
            if command_result.status == CommandStatus.COMPLETED:
                return self._format_command_result(command_result)
            else:
                return {
                    "status": "failed",
                    "return_code": command_result.return_code,
                    "stdout": command_result.stdout,
                    "stderr": command_result.stderr,
                    "execution_time": command_result.execution_time,
                    "error_message": command_result.error_message or "未知错误"
                }
        else:
            return {
                "status": "timeout",
                "return_code": -1,
                "stdout": "",
                "stderr": "",
                "execution_time": max_wait_time,
                "error_message": f"命令执行超时（等待超过{max_wait_time}秒）"
            }

    def _format_command_result(self, result: CommandResult) -> Dict[str, Any]:
        """格式化命令执行结果"""
        return {
            "status": result.status.value,
            "return_code": result.return_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "execution_time": result.execution_time,
            "error_message": result.error_message
        }
    def _format_args(self, kwargs: Dict[str, Any]) -> str:
        command = kwargs.get("command")
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


    def _get_success_message(self, result: dict) -> str:
        """生成成功消息"""
        # 优先检查 stderr 和 error_message
        return ""

async def execute_bash_command_async(
    command: str,
    working_directory: str = ".",
    timeout: Optional[int] = None,
    use_queue: bool = False,
    callback: Optional[Callable[[CommandResult], None]] = None
) -> str:
    """
    快速执行Bash命令的便捷函数（异步版本）

    Args:
        command: 要执行的命令
        working_directory: 工作目录
        timeout: 超时时间
        use_queue: 是否使用队列
        callback: 执行完成后的回调函数

    Returns:
        命令ID
    """
    executor = get_bash_executor()

    if use_queue:
        return await executor.queue_command(command, working_directory, timeout, callback)
    else:
        return await executor.execute_command(command, working_directory, timeout, callback)