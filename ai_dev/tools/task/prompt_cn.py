import asyncio

from ai_dev.utils.subagent import get_agent_descriptions

prompt: str = f"""启动一个新的 Agent，用于自主处理复杂的多步骤任务。
可用的 Agent 类型及其可访问的工具如下：  
{asyncio.run(get_agent_descriptions())}

使用 TaskTool 工具 时，必须指定 `agent_name` 参数以选择要使用的 Agent 类型。

## 何时使用 TaskTool 工具:
- 当执行符合 Agent 描述中的复杂任务时使用此工具启动Agent

**注意**: 当遇到复杂任务时，优先检查是否有可用的Agent可以处理，如果有则优先使用Agent进行处理，这样可以大幅节约token消耗

## 何时不使用 TaskTool 工具:
- 如果你想读取特定文件路径，请使用 `FileReadTool` 或 `GlobTool`，这样可以更快找到匹配。
- 如果你要查找特定类定义（如 `class Foo`），请使用 `GlobTool`，以更快找到匹配。
- 如果你只需在特定文件或 2–3 个文件中搜索代码，请使用 `FileReadTool`，而不是 `TaskTool` 工具，以加快查找速度。
- 其他与前述 `TaskTool` 描述无关的任务。

## 使用注意事项:
1. 尽可能同时启动多个 Agent以最大化性能；
    - 为此，在单条消息中包含多个工具调用。
    - 并发 Agent 数量最多为 20 个。
2. 当 Agent 完成任务时，它会返回一条消息给你。
    - Agent 返回的结果对用户不可见。
    - 若要向用户显示结果，应发送一条文本消息，简明概括 Agent 的结果。
3. 每次 Agent 调用都是无状态的：
    - 无法向 Agent 发送额外消息，也无法在最终报告之外与 Agent 交流。
    - 因此，提示内容**必须详细描述任务**，并明确指定 Agent 在最终报告中应返回哪些信息。
4. 一般可以信任 Agent 的输出。
5. 明确告诉 Agent，你希望它写代码还是仅进行研究（搜索、文件读取、网络获取等），因为它不了解用户意图。
6. 如果 Agent 描述中提到应主动使用，尽量在用户未请求前使用它，并根据实际情况判断。

## 使用示例:

```
<example_agent_descriptions>
"code-reviewer": use this agent after you are done writing a signficant piece of code
"greeting-responder": use this agent when to respond to user greetings with a friendly joke
</example_agent_description>
```

```
<example>
user: "Please write a function that checks if a number is prime"
assistant: Sure let me write a function that checks if a number is prime
assistant: First let me use the FileWriteTool tool to write a function that checks if a number is prime
assistant: I'm going to use the FileWriteTool tool to write the following code:
<code>
def is_prime(n):
    if n <= 1:
        return False
    for i in range(2, n):
        if n % i == 0:
            return False
    return True
</code>
<commentary>
Since a signficant piece of code was written and the task was completed, now use the code-reviewer agent to review the code
</commentary>
assistant: Now let me use the code-reviewer agent to review the code
assistant: Uses the TaskTool tool to launch the with the code-reviewer agent 
</example>
```

```
<example>
user: "Hello"
<commentary>
Since the user is greeting, use the greeting-responder agent to respond with a friendly joke
</commentary>
assistant: "I'm going to use the Task tool to launch the with the greeting-responder agent"
</example>
```"""