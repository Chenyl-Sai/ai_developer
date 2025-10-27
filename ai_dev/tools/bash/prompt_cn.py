from ai_dev.constants.product import PRODUCT_NAME

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

prompt: str = f"""在一个持久的 shell 会话中执行指定的 bash 命令，可选设置超时时间，确保正确的处理和安全措施。

在执行命令之前，请遵循以下步骤：

1. 目录验证（Directory Verification）：
   - 如果命令将创建新的目录或文件，首先使用 `FileListTool` 工具验证父目录是否存在且位置正确。
   - 例如，在运行 `"mkdir foo/bar"` 之前，先使用 `FileListTool` 检查 "foo" 是否存在，并确认它是预期的父目录。

2. 安全检查（Security Check）：
   - 出于安全考虑以及防止提示注入攻击，某些命令受到限制或被禁止。如果使用了被禁止的命令，将会收到错误信息解释限制原因，请向用户说明该错误。
   - 验证命令不属于被禁止的命令列表：{", ".join(BANNED_COMMANDS)}。

3. 命令执行（Command Execution）：
   - 确保命令参数被正确引用（proper quoting）后，执行该命令。
   - 捕获命令的输出结果。

4. 输出处理（Output Processing）：
   - 如果输出超过 {MAX_OUTPUT_LENGTH} 个字符，输出将在返回之前被截断。
   - 为用户显示做好输出内容的准备。

5. 返回结果（Return Result）：
   - 提供处理后的命令输出结果。
   - 如果执行过程中出现任何错误，也应将其包含在输出中。

使用说明（Usage notes）：
  - **命令参数是必需的**。
  - 你可以指定一个**可选的超时时间（单位：毫秒）**，最大为 600000ms（10 分钟）。如果未指定，命令将在 30 分钟后自动超时。
  - **非常重要（VERY IMPORTANT）**：
    - **禁止使用**诸如 find 和 grep 等搜索命令。请改用 GrepTool、GlobTool 或 TaskTool 来进行搜索。
    - **禁止使用**诸如 cat、head、tail 和 ls 等文件读取命令。请改用 FileReadTool 和 FileListTool 来读取文件。
  - 当执行多个命令时，请使用 ; 或 && 运算符将它们分隔。
  - 重要（IMPORTANT）：
    - 所有命令**共享同一个 shell 会话**。
    - Shell 状态（环境变量、虚拟环境、当前目录等）在命令之间是**持久的**。例如，如果在某个命令中设置了一个环境变量，该变量将在后续命令中继续生效。
  - 请尽量在整个会话中保持相同的工作目录：使用**绝对路径**，并避免使用 `cd`。只有当用户明确要求时，才可以使用 `cd`。
    ```  
    <good-example>
    pytest /foo/bar/tests
    </good-example>
    <bad-example>
    cd /foo/bar && pytest tests
    </bad-example>
    ```

# 使用 Git 提交更改

当用户要求你创建一个新的 git 提交（git commit）时，请严格按照以下步骤执行：

1. 首条消息必须包含三个 tool_use 块（非常重要！），务必在同一条消息中包含以下三个 tool_use 操作，否则用户会感觉响应缓慢：
  - 运行 `git status` 命令，查看所有未跟踪（untracked）的文件。
  - 运行 `git diff` 命令，查看所有已暂存（staged）和未暂存（unstaged）的更改内容。
  - 运行 `git log` 命令，查看最近的提交信息，以便遵循该仓库的提交信息风格。

2. 确定需要提交的文件
  - 根据会话开始时提供的 git 上下文，判断哪些文件与本次提交相关。
  - 将相关的未跟踪文件添加到暂存区（staging area）。
  - 不要提交那些在本次会话开始时就已经被修改、且与本次提交无关的文件。

3. 分析所有已暂存的更改并撰写提交信息

    将分析过程用 <commit_analysis> 标签包裹，如下所示：
    ```
    <commit_analysis>
    - 列出被更改或新增的文件  
    - 概述更改的性质（例如：新增功能、新特性增强、修复 bug、代码重构、测试、文档等）  
    - 推测这些更改背后的目的或动机  
    - 不要使用任何工具进一步探索代码，只使用现有 git 上下文信息  
    - 评估这些更改对整个项目的影响  
    - 检查是否有不应提交的敏感信息  
    - 撰写简洁（1–2 句）的提交信息，重点阐述“为什么”而不是“做了什么”  
    - 保持语言清晰、简练、准确  
    - 确保提交信息准确反映更改的目的（例如：“add” 表示全新功能，“update” 表示改进现有功能，“fix” 表示修复问题）  
    - 避免使用泛泛的词汇（如 “Update” 或 “Fix”）而不说明上下文  
    - 最后审查信息，确保表达准确且有意义  
    </commit_analysis>
    ```

4. 创建提交

- 创建提交时，提交信息结尾必须包含以下标记： `🤖 Generated with {PRODUCT_NAME}`

- 为确保格式正确，必须使用 HEREDOC 形式传递提交信息，例如：
    ```
    <example>
    git commit -m "$(cat <<'EOF'
       Commit message here.
    
       🤖 Generated with {PRODUCT_NAME}
       EOF
       )"
    </example>
    ```

5. 处理 pre-commit hook
- 如果提交失败（被 pre-commit hook 修改了文件），请**重试一次提交**以包含这些自动更改。
- 若再次失败，通常表示 hook 阻止了提交。
- 如果提交成功但文件被 hook 自动修改，必须使用 git commit --amend 将修改一并提交。

6. 验证提交

    最后，运行 `git status`，确保提交成功。

**重要注意事项**
- 若可能，使用 `git commit -am` 将暂存与提交合并，以提升速度。
- 但**不要**使用 `git add` . 来盲目暂存所有文件，以免提交不相关更改。
- **禁止**修改 git 配置（git config）。
- **禁止**推送到远程仓库（git push）。
- **禁止**使用带 `-i` 参数的交互式命令（如 `git rebase -i` 或 `git add -i`）。
- 如果没有更改（无未跟踪文件且无修改），**不要创建空提交**。
- 提交信息必须**有意义且简明**，重点解释更改的目的而非仅描述更改内容。
- 提交完成后**返回空响应**——用户将直接看到 git 命令的输出。

# 创建拉取请求（Pull Request）

使用 `gh` 命令（通过 Bash 工具）来完成所有与 GitHub 相关的任务，包括 issues、pull requests、checks 和 releases。
如果提供了一个 GitHub URL，应使用 gh 命令获取所需信息。

**重要说明**: 
当用户要求你创建一个 Pull Request（PR） 时，请严格遵循以下步骤：
1. 理解当前分支的状态

    你必须在一条消息中发送多个 tool_use 块（非常重要！否则用户会感到响应缓慢）：
- 运行 `git status` 命令，查看所有未跟踪（untracked）的文件。
- 运行 `git diff` 命令，查看所有已暂存（staged）与未暂存（unstaged）的更改。
- 检查当前分支是否跟踪了远程分支，并确认其是否与远程同步，以判断是否需要推送（push）。
- 运行 `git log` 和 `git diff main...HEAD`，了解当前分支自从从 `main` 分支分叉（diverge）以来的完整提交历史。
2. 如果需要，创建新分支
3. 如果需要，提交本地更改
4. 如果需要，推送到远程仓库

    使用 git push -u 将本地分支推送到远程仓库，并建立跟踪关系。
5. 分析 Pull Request 内容并撰写摘要

   - 分析所有将包含在 PR 中的更改（不仅是最后一次提交，而是**所有自从从 main 分支分叉以来的提交**）。
   - 将分析过程包裹在 <pr_analysis> 标签中，例如：
       ```
       <pr_analysis>
       - 列出自从从 main 分支分叉以来的所有提交  
       - 概述更改的性质（如：新功能、新特性增强、修复 bug、重构、测试、文档等）  
       - 推测这些更改的目的或动机  
       - 评估这些更改对整个项目的影响  
       - 不要使用额外工具探索代码，仅使用当前 git 上下文信息  
       - 检查是否存在不应被提交的敏感信息  
       - 撰写简洁（1–2 条要点）的 Pull Request 摘要，重点关注“为什么”而非“做了什么”  
       - 确保摘要准确反映自分叉以来的所有更改  
       - 语言应清晰、简洁、准确  
       - 提交摘要必须准确体现更改的目的（如 "add" 表示新增功能，"update" 表示改进现有功能，"fix" 表示修复错误等）  
       - 避免使用泛泛的词汇（如 “Update” 或 “Fix”）而不说明上下文  
       - 最后审查摘要，确保内容真实、清晰且有意义  
       </pr_analysis>
       ```

完成上述步骤后，再使用 gh pr create 命令创建 Pull Request，并附上在 <pr_analysis> 中整理的摘要作为说明内容。

**重要说明**
- **返回空响应** —— 用户将直接看到 gh 命令的输出结果。
- **绝对禁止修改 git 配置（git config）。**"""