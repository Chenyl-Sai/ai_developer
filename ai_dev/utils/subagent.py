import asyncio, frontmatter, logging

from pydantic import BaseModel, Field
from typing_extensions import Literal
from pathlib import Path
from async_lru import alru_cache
from watchdog.events import FileSystemEvent, FileSystemEventHandler, DirDeletedEvent, FileDeletedEvent
from watchdog.observers import Observer

from ai_dev.core.global_state import GlobalState

logger = logging.getLogger(__name__)

class SubAgentConfig(BaseModel):
    """代理配置"""
    agent_name: str = Field(..., description="代理名称,唯一标识")
    agent_type: Literal["built-in", "user", "project"] = Field(..., description="代理类型")
    description: str = Field(..., description="代理描述")
    system_prompt: str | None = Field(default=None, description="提示词")
    tools: str | list[str] = Field(default='*', description="可用工具列表")
    model: str | None = Field(default=None, description="使用的模型")

build_in_general_agent_description = "General-purpose agent for researching complex questions, searching for code, and executing multi-step tasks"
build_in_general_agent_description_cn = "通用型 Agent，用于研究复杂问题、搜索代码以及执行多步骤任务。"

build_in_general_agent_system_prompt = """You are a general-purpose agent. Given the user's task, use the tools available to complete it efficiently and thoroughly.

When to use your capabilities:
- Searching for code, configurations, and patterns across large codebases
- Analyzing multiple files to understand system architecture  
- Investigating complex questions that require exploring many files
- Performing multi-step research tasks

Guidelines:
- For file searches: Use Grep or Glob when you need to search broadly. Use FileRead when you know the specific file path.
- For analysis: Start broad and narrow down. Use multiple search strategies if the first doesn't yield results.
- Be thorough: Check multiple locations, consider different naming conventions, look for related files.
- Complete tasks directly using your capabilities."""
build_in_general_agent_system_prompt_cn = """你是一个通用型 Agent。根据用户的任务，使用可用工具高效且全面地完成任务。

使用场景:
- 在大型代码库中搜索代码、配置文件和模式
- 分析多个文件以理解系统架构
- 调查需要遍历多个文件的复杂问题
- 执行多步骤的研究任务

操作指南:
- **文件搜索**: - 当需要广泛搜索时，使用 GrepTool 或 GlobTool。当已知具体文件路径时，使用 FileReadTool。
- **分析任务**: - 先广泛搜索，再逐步缩小范围。若第一次搜索未得到结果，可使用多种搜索策略。
- **保持彻底性**: - 检查多个位置，考虑不同命名方式，查找相关文件。
- **直接完成任务**: - 使用你的能力直接执行任务，不依赖用户进一步指示。"""

# Built-in general-purpose agent as fallback
BUILTIN_GENERAL_PURPOSE: SubAgentConfig = SubAgentConfig(
    agent_name='general-purpose',
    agent_type='built-in',
    description=build_in_general_agent_description_cn,
    tools='*',
    system_prompt=build_in_general_agent_system_prompt_cn
)

async def scan_sub_agent_directory(directory: Path, agent_type: Literal["user", "project"]) -> list[SubAgentConfig]:
    if not directory.exists():
        return []
    sub_agents: list[SubAgentConfig] = []
    for file in directory.iterdir():
        if file.is_dir():
            continue
        if file.suffix != '.md':
            continue
        try:
            post = frontmatter.load(str(file))
            data = post.metadata
            content = post.content

            # Validate required fields
            if not data.get("agent_name") or not data.get("description"):
                logger.warning(f"Skipping {file}:: missing required fields (name, description)")
                continue

            sub_agents.append(SubAgentConfig(
                agent_name=data.get("agent_name"),
                agent_type=agent_type,
                description=data.get("description"),
                system_prompt=data.get("system_prompt"),
                tools=data.get("tools"),
                model=data.get("model"),
            ))

        except Exception as e:
            logger.warning(f"Failed to parse agent file {file}:", exc_info=e)
            continue

    return []


async def load_all_sub_agents() -> dict[str, list[SubAgentConfig]]:
    try:
        user_dir = Path.home() / ".ai_dev" / "agents"
        project_dir = Path(GlobalState.get_working_directory()) / ".ai_dev" / "agents"
        # 内置agent
        build_ins = [BUILTIN_GENERAL_PURPOSE]

        # 加载外部agent
        load_outer_agent_tasks = [scan_sub_agent_directory(user_dir, "user"),
                                  scan_sub_agent_directory(project_dir, "project")]
        (users, projects) = await asyncio.gather(*load_outer_agent_tasks)

        # 根据project>user>build-in的优先级保留
        available_sub_agents: dict[str, SubAgentConfig] = {}
        for sub_agent in build_ins:
            available_sub_agents[sub_agent.agent_name] = sub_agent
        for sub_agent in users:
            available_sub_agents[sub_agent.agent_name] = sub_agent
        for sub_agent in projects:
            available_sub_agents[sub_agent.agent_name] = sub_agent
        return {
            "activeAgents": list(available_sub_agents.values()),
            "allAgents": build_ins + users + projects
        }
    except Exception as e:
        logger.warning("Failed to load agents, falling back to built-in:", exc_info=e)
        return {
            "activeAgents": [BUILTIN_GENERAL_PURPOSE],
            "allAgents": [BUILTIN_GENERAL_PURPOSE]
        }

@alru_cache()
async def get_all_sub_agents() -> list[SubAgentConfig]:
    return (await load_all_sub_agents()).get("allAgents")

@alru_cache()
async def get_available_sub_agents() -> list[SubAgentConfig]:
    return (await load_all_sub_agents()).get("activeAgents")

@alru_cache()
async def get_available_sub_agent_names() -> list[str]:
    return [agent.agent_name for agent in (await load_all_sub_agents()).get("activeAgents")]

@alru_cache()
async def get_sub_agent_by_name(name: str) -> SubAgentConfig:
    agents = await get_available_sub_agents()
    return next(filter(lambda a: a.agent_name == name, agents), None)

@alru_cache()
async def get_agent_descriptions() -> str:
    agents = await get_available_sub_agents()
    return "\n".join(
        f"- {agent.agent_name}: {agent.description} (Tools: {', '.join(agent.tools) if isinstance(agent.tools, list) else '*'})"
        for agent in agents
    )
def clear_all_cache() -> None:
    get_all_sub_agents.cache_clear()
    get_available_sub_agents.cache_clear()
    get_sub_agent_by_name.cache_clear()
    get_available_sub_agent_names.cache_clear()
    get_agent_descriptions.cache_clear()

file_watchers: list[Observer] = []

class MyEventHandler(FileSystemEventHandler):
    def on_created(self, event: FileSystemEvent) -> None:
        clear_all_cache()
    def on_modified(self, event: FileSystemEvent) -> None:
        clear_all_cache()
    def on_deleted(self, event: DirDeletedEvent | FileDeletedEvent) -> None:
        clear_all_cache()

def start_watcher():
    user_dir = Path.home() / ".ai_dev" / "agents"
    project_dir = Path(GlobalState.get_working_directory()) / ".ai_dev" / "agents"
    for dir in [user_dir, project_dir]:
        if dir.exists():
            observer = Observer()
            observer.schedule(MyEventHandler(), str(dir), recursive=False)
            observer.start()
            file_watchers.append(observer)

def stop_watcher():
    for observer in file_watchers:
        observer.stop()
        observer.join()
