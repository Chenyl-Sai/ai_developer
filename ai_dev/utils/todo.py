import json
from pathlib import Path
from pydantic import BaseModel, Field

from ai_dev.tools.todo_write import TodoItem
from ai_dev.core.global_state import GlobalState
from datetime import datetime
from typing_extensions import Literal
from ai_dev.utils.logger import agent_logger

class TodoItemStorage(TodoItem):
    create_at: datetime
    update_at: datetime
    previous_status: Literal["pending", "in_progress", "completed"]

class TodoItemStorageConfig(BaseModel):
    max_todos: int = Field(default=100)
    auto_archive_completed: bool = False

DEFAULT_CONFIG = TodoItemStorageConfig(max_todos=100, auto_archive_completed=False)

async def get_todos(agent_id: str) -> list[TodoItemStorage]:
    """根据agent_id获取待办列表

    Args:
        agent_id (str): agent_id
    Returns:
        list[TodoItemStorage] 待办列表
    """
    # 获取agent_id对应的待办列表存储文件路径
    todo_file_path = get_todo_file_path(agent_id)

    # 如果文件不存在，返回空列表
    if not todo_file_path.exists():
        return []

    try:
        # 读取文件并解析成list[TodoItemStorage]
        with open(todo_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 将存储数据转换为TodoItemStorage对象并直接返回
        storage_items = []
        for item_data in data.get("todos", []):
            # 将字符串时间转换为datetime对象
            item_data["create_at"] = datetime.fromisoformat(item_data["create_at"])
            item_data["update_at"] = datetime.fromisoformat(item_data["update_at"])
            storage_items.append(TodoItemStorage(**item_data))

        return storage_items

    except Exception as e:
        # 如果读取失败，返回空列表
        agent_logger.error(f"警告: 读取待办列表文件失败", exception=e)
        return []


async def set_todos(todos: list[TodoItem], agent_id: str) -> list[TodoItemStorage]:
    """保存/更新待办列表

    Args:
        todos (list[TodoItem]): 待办列表
        agent_id (str): agent_id

    Returns:
        None
    """
    # 获取配置
    config_manager = GlobalState.get_config_manager()
    if config_manager:
        max_todos = config_manager.get("todo_settings.max_todos", 100)
        auto_archive_completed = config_manager.get("todo_settings.auto_archive_completed", False)
    else:
        max_todos = DEFAULT_CONFIG.max_todos
        auto_archive_completed = DEFAULT_CONFIG.auto_archive_completed

    # 检查待办列表数量是否满足要求
    if len(todos) > max_todos:
        raise ValueError(f"待办列表数量超过限制: {len(todos)} > {max_todos}")

    # 判断是否自动归档，自动归档的话将completed状态的过滤掉
    if auto_archive_completed:
        todos = [todo for todo in todos if todo.status != "completed"]

    # 获取之前的待办列表
    existing_todos = await get_todos(agent_id)
    existing_todos_dict = {todo.id: todo for todo in existing_todos}

    # 对比新旧列表，将入参变成TodoItemStorage对象并更新create_at、update_at、previous_status
    storage_items = []
    now = datetime.now()

    for todo in todos:
        existing_todo = existing_todos_dict.get(todo.id)

        if existing_todo:
            # 更新现有任务
            previous_status = existing_todo.status
            create_at = existing_todo.create_at if hasattr(existing_todo, 'create_at') else now
            storage_item = TodoItemStorage(
                id=todo.id,
                content=todo.content,
                status=todo.status,
                priority=todo.priority,
                create_at=create_at,
                update_at=now,
                previous_status=previous_status
            )
        else:
            # 创建新任务
            storage_item = TodoItemStorage(
                id=todo.id,
                content=todo.content,
                status=todo.status,
                priority=todo.priority,
                create_at=now,
                update_at=now,
                previous_status="pending"
            )
        storage_items.append(storage_item)

    # 对列表进行排序，先排status、再排priority、最后排update_at
    def sort_key(item):
        status_order = {"in_progress": 0, "pending": 1, "completed": 2}
        priority_order = {"high": 0, "medium": 1, "low": 2}
        return (
            status_order.get(item.status, 3),
            priority_order.get(item.priority, 3),
            item.update_at
        )

    storage_items.sort(key=sort_key)

    # 将待办列表写入文件
    todo_file_path = get_todo_file_path(agent_id, True)

    try:
        # 准备存储数据
        storage_data = {
            "todos": [
                {
                    "id": item.id,
                    "content": item.content,
                    "status": item.status,
                    "priority": item.priority,
                    "create_at": item.create_at.isoformat(),
                    "update_at": item.update_at.isoformat(),
                    "previous_status": item.previous_status
                }
                for item in storage_items
            ]
        }

        # 写入文件
        with open(todo_file_path, 'w', encoding='utf-8') as f:
            json.dump(storage_data, f, ensure_ascii=False, indent=2)
        return storage_items
    except Exception as e:
        agent_logger.error(f"错误: 保存待办列表文件失败", exception=e)
        raise

async def delete_todo_file_if_need(agent_id: str):
    """清理待办缓存文件"""
    todos = await get_todos(agent_id)
    # 如果全部都是completed
    remains = [todo for todo in todos if todo.status != 'completed']
    if len(remains) == 0:
        file_path = get_todo_file_path(agent_id)
        if file_path.exists():
            file_path.unlink()

def get_todo_file_path(agent_id: str, for_write: bool = False):
    working_dir = GlobalState.get_working_directory()
    todo_dir = Path(working_dir) / ".ai_dev" / "todos"
    if for_write:
        todo_dir.mkdir(parents=True, exist_ok=True)
    todo_file_path = todo_dir / f"{agent_id}.json"
    return todo_file_path