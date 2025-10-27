"""
SubAgentGraph - 基于LangGraph的ReAct结构子代理图
"""

import asyncio
import copy
from typing import Dict, Any, List, Optional, Literal, Annotated

from langgraph.config import get_stream_writer
from langgraph.errors import GraphInterrupt
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessageChunk, AIMessage, ToolCall
from langchain_core.tools import BaseTool
from langgraph.types import Command, Interrupt, interrupt

from .event_manager import event_manager, Event, EventType
from .global_state import GlobalState
from ..constants.product import MAIN_AGENT_NAME, MAIN_AGENT_ID
from ..models.state import MyAgentState, accept_new_merger
from ai_dev.permission.permission_manager import PermissionManager, PermissionDecision, UserPermissionChoice
from ..tools import MyBaseTool
from ..utils.logger import agent_logger
from ..utils.compact import check_auto_compact
from ..utils.message import estimate_token_for_chunk_message
from ..utils.tool import get_tool_by_name

class SubAgentState(MyAgentState):
    """SubAgent专用状态类"""
    tool_calls: List[Dict[str, Any]] = []
    current_iteration: int = 0
    agent_id: Optional[str] = None
    user_canceled: Annotated[bool, accept_new_merger] = False


class ReActAgent:
    """基于LangGraph的ReAct结构子代理图"""

    def __init__(
            self,
            name: str,
            system_prompt: list[str],
            tools: List[BaseTool],
            is_main_agent: bool = True,
            context: Optional[Dict[str, Any]] = None,
            model: Optional[str] = None,
    ):
        """
        初始化SubAgentGraph

        Args:
            system_prompt: 系统提示词
            tools: 可用的工具列表
            context: 上下文信息
            model: 使用的模型名称
        """
        self.name = name
        self.system_prompt = system_prompt
        self.context = context or {}
        self.is_main_agent = is_main_agent

        # 初始化工具列表
        self.tools = tools

        # 初始化模型管理器
        self.model_name = model or GlobalState.get_config_manager().get_default_model()

        self.model = GlobalState.get_model_manager().get_model(self.model_name, tags=["main"])

        self.bound_model = self.model.bind_tools(self.tools)

        # 构建LangGraph
        self.graph = self._build_graph()

        # 订阅用户中断请求
        self._user_canceled = False
        event_manager.subscribe(EventType.USER_CANCEL, self._process_user_cancel)

        self._resume_task_process_lock = asyncio.Lock()
        self.resumed_tasks = []

    def _process_user_cancel(self, event):
        self._user_canceled = True

    def _generate_agent_id(self) -> str:
        """生成唯一的agent_id"""
        import uuid
        return f"sub_agent_{uuid.uuid4().hex[:8]}"

    def _build_system_message(self) -> SystemMessage:
        """构建系统消息 - 直接使用传入的系统提示词"""
        system_prompt = "\n".join(self.system_prompt)
        return SystemMessage(content=system_prompt)

    def _build_graph(self) -> CompiledStateGraph:
        """构建LangGraph状态图"""
        workflow = StateGraph(SubAgentState)

        # 添加节点
        workflow.add_node("reason", self._reason_node)
        workflow.add_node("check_permissions", self._check_permissions_node)

        # 只执行非TaskTool任务的工具节点， 非TaskTool的权限中断都已经在前置完成了，这里不会再有中断、恢复的幂等问题了
        workflow.add_node("execute_tools", self._execute_tools_node)

        # 给主图增加20个预设的TaskTool并行执行节点，与普通工具节点分开(这个中断)
        if self.is_main_agent:
            for i in range(20):
                workflow.add_node(f"task_node_{i}", self._define_task_tool(i))

        # 设置入口点
        workflow.set_entry_point("reason")

        # 添加条件边
        workflow.add_conditional_edges(
            "reason",
            self._should_continue,
            {
                "continue": "check_permissions",
                "end": END,
                "interrupt": END
            }
        )

        workflow.add_conditional_edges(
            "check_permissions",
            self._should_execute_tools,
            {
                "execute": "execute_tools",
                "task_node_0": "task_node_0",
                "task_node_1": "task_node_1",
                "task_node_2": "task_node_2",
                "task_node_3": "task_node_3",
                "task_node_4": "task_node_4",
                "task_node_5": "task_node_5",
                "task_node_6": "task_node_6",
                "task_node_7": "task_node_7",
                "task_node_8": "task_node_8",
                "task_node_9": "task_node_9",
                "task_node_10": "task_node_10",
                "task_node_11": "task_node_11",
                "task_node_12": "task_node_12",
                "task_node_13": "task_node_13",
                "task_node_14": "task_node_14",
                "task_node_15": "task_node_15",
                "task_node_16": "task_node_16",
                "task_node_17": "task_node_17",
                "task_node_18": "task_node_18",
                "task_node_19": "task_node_19",
                "skip": "reason",
                "interrupt": END
            }
        )

        # 工具执行完始终流转到LLM
        workflow.add_edge("execute_tools", "reason")

        # TaskNode执行完返回llm
        if self.is_main_agent:
            for i in range(10):
                workflow.add_edge(f"task_node_{i}", "reason")

        # 编译图并添加中断支持
        from langgraph.checkpoint.memory import InMemorySaver
        memory = InMemorySaver()

        # 如果当前是主图，则设置checkpointer，子图不需要设置，自动使用主图的checkpointer
        return workflow.compile(
            checkpointer=memory if self.is_main_agent else None,
        )

    async def _reason_node(self, state: SubAgentState):
        """推理节点 - 分析用户需求并决定下一步行动"""

        messages = state.messages
        # 对消息进行压缩
        processed_messages, compacted = await check_auto_compact(messages)
        if compacted:
            messages = processed_messages

        # 调用模型前，如果有用户pending，拼接进去
        new_user_inputs = await self._process_user_input_pending(state)
        if new_user_inputs:
            messages.extend(new_user_inputs)

        # 调用模型之前判断是否有Event.INTERRUPT事件，如果有则返回退出标记
        if self._user_canceled:
            return {
                "user_canceled": True,
            }

        # 不将系统消息拼接到state.message中，而是请求之前直接拼接
        request_messages = [self._build_system_message()] + messages
        agent_logger.log_model_call(state.agent_id, self.model_name, request_messages)
        ai_message = await self.bound_model.ainvoke(request_messages)
        # 记录模型响应信息
        agent_logger.log_model_response(state.agent_id, self.model_name, ai_message)

        return {
            "tool_calls": ai_message.tool_calls,
            "messages": ai_message if not compacted else {
                "_replace": True,
                "messages": messages + [ai_message]
            },
            "current_iteration": state.current_iteration + 1
        }

    async def _check_permissions_node(self, state: SubAgentState):
        """权限检查节点 - 检查工具执行权限"""
        if not state.tool_calls:
            return {
                "user_canceled": self._user_canceled
            }

        # 如果用户中断，不用请求权限了，直接中断
        if self._process_interrupt_when_tool_execute(self._user_canceled, state):
            return {
                "user_canceled": True,
                "messages": state.messages,
            }

        # 检查每个工具调用的权限
        allowed_tool_calls = []
        denied_tool_calls = []
        ask_requests = []  # 存储需要问询的(工具调用, 权限请求)对

        for tool_call in state.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})

            # 检查权限
            decision, request = await GlobalState.get_permission_manager().check_permission(tool_name, tool_args, state.agent_id,
                                                                               GlobalState.get_working_directory())

            if decision == PermissionDecision.ALLOW:
                allowed_tool_calls.append(tool_call)
            elif decision == PermissionDecision.DENY:
                denied_tool_calls.append(tool_call)
                # 添加拒绝消息
                error_message = ToolMessage(
                    content=f"权限被拒绝: {tool_name}",
                    tool_call_id=tool_call.get("id"),
                )
                state.messages.append(error_message)
            elif decision == PermissionDecision.ASK:
                ask_requests.append((tool_call, request))

        # 如果有需要询问的工具调用，循环处理每个ASK请求
        user_refuse = False
        # 整理好所有需要中断的任务
        need_interrupt_requests = []
        for tool_call, request in ask_requests:
            interrupt_info = request.get_display_info()
            if not interrupt_info.get("success", False):
                    reason = interrupt_info.get("fail_reason")
                    error_message = ToolMessage(
                        content=reason,
                        tool_call_id=tool_call.get("id"),
                    )
                    state.messages.append(error_message)
            else:
                need_interrupt_requests.append((tool_call, request, interrupt_info))

        if need_interrupt_requests:
            # 一次性弹出所有中断,如果用户中断，那么前端来一次性将所有授权全部拒绝，不要后端增加其他逻辑，会导致中断索引对不上
            for tool_call, request, interrupt_info in need_interrupt_requests:
                user_choice = interrupt(interrupt_info)
                # 映射用户选择
                if user_choice == "1":
                    choice = UserPermissionChoice.ALLOW_ONCE
                elif user_choice == "2":
                    choice = UserPermissionChoice.ALLOW_SESSION
                else:
                    choice = UserPermissionChoice.DENY
                # 应用用户选择并决定是否允许执行
                is_allowed = GlobalState.get_permission_manager().apply_user_choice(request, choice)
                if is_allowed:
                    allowed_tool_calls.append(tool_call)
                else:
                    user_refuse = True
                    denied_tool_calls.append(tool_call)
                    error_message = ToolMessage(
                        content=f"权限被拒绝: {tool_call['name']}",
                        tool_call_id=tool_call.get("id"),
                    )
                    state.messages.append(error_message)

        if self._process_interrupt_when_tool_execute(user_refuse, state):
            # 这时候真正的中断
            import time
            await event_manager.publish(Event(
                event_type=EventType.USER_CANCEL,
                data={
                    "source": "keyboard",
                },
                source="ReActAgent",
                timestamp=time.time()
            ))
            # 返回用户拒绝,结束图的执行
            return {
                "user_canceled": True,
                "messages": state.messages
            }

        return {
            "tool_calls": allowed_tool_calls,
            "messages": state.messages
        }

    def _define_task_tool(self, index: int):
        """
        创建任务执行节点方法工厂，每个节点只处理与自己创建时下标想通的那一个子任务
        """

        async def task_tool_node(state: SubAgentState, config):
            # 只执行TaskTool类型的任务
            task_tool_calls = [tool_call for tool_call in state.tool_calls if tool_call.get("name") == "TaskTool"]
            if task_tool_calls and len(task_tool_calls) >= index:
                # 只执行下标匹配的那一个
                current_task = task_tool_calls[index]
                # 没有中断的时候继续执行
                if not self._process_interrupt_when_tool_execute(self._user_canceled, state):
                    # 手动弄一些参数进去，这里不能直接修改state中的ToolCall，因为state中的信息回变成历史消息重新传给模型，会污染模型调用方法的参数！
                    copied_tool_call: ToolCall = copy.deepcopy(current_task)
                    args = copied_tool_call.setdefault("args", {})
                    task_id = None
                    async with self._resume_task_process_lock:
                        resume_task_ids = (config.get("configurable", {}) if config else {}).get("resume_task_ids", [])
                        if resume_task_ids and len(resume_task_ids) > 0:
                            # 从resume_task_ids中获取后缀与当前node index相符的那个任务
                            for resume_task_id in resume_task_ids:
                                node_index = resume_task_id.rsplit("_", 1)[-1]
                                if node_index == str(index) and resume_task_id not in self.resumed_tasks:
                                    task_id = resume_task_id
                                    self.resumed_tasks.append(task_id)
                                    break
                    args["context"] = {
                        "agent_id": state.agent_id,
                        "tool_id": copied_tool_call.get("id"),
                        "task_id": task_id,
                        # 所有的task节点是并列的，无标识的，为了防止恢复的时候混乱，必须给每个task标记是哪个node执行的
                        # 否则中断恢复的时候就会导致node_0恢复了node_1的内容
                        # 应为恢复的时候依赖task_id，所以task_id的分配也必须要匹配
                        "_node_index": index,
                    }
                    try:
                        from ai_dev.utils.tool import task_tool
                        tool_result = await task_tool.ainvoke(copied_tool_call)
                    except GraphInterrupt:
                        raise
                    except Exception as e:
                        # 处理单个工具执行失败
                        tool_result = ToolMessage(
                            content=f"工具执行失败: {str(e)}",
                            tool_call_id=copied_tool_call.get("id"),
                        )
                        agent_logger.error("工具执行失败", exception=e)
                    state.messages.append(tool_result)
                return {
                    "user_canceled": self._user_canceled,
                    "messages": state.messages,
                }
            # 没有自己的任务就什么也不做
            return {}

        return task_tool_node

    async def _execute_tools_node(self, state: SubAgentState):
        """异步执行工具节点 - 智能并行执行"""
        # 分类工具调用
        parallelizable_tasks = []
        sequential_tools = []

        # 判断是否有Event.INTERRUPT事件，如果有则为所有tool_call返回用户中断执行状态，并立即返回中断执行，
        #  虽然后续暂时不再执行模型调用，但是历史消息也必须要保证ToolCall请求返回ToolMessage
        if self._process_interrupt_when_tool_execute(self._user_canceled, state):
            return {
                "user_canceled": True,
                "messages": state.messages
            }

        for tool_call in state.tool_calls:
            # 跳过TaskTool，task_tool_node会单独处理它
            if tool_call.get("name") == "TaskTool":
                continue
            # 手动弄一些参数进去
            copied_tool_call = copy.deepcopy(tool_call)
            args = copied_tool_call.setdefault("args", {})
            args["context"] = {
                "agent_id": state.agent_id,
                "tool_id": copied_tool_call.get("id"),
            }
            tool: MyBaseTool = get_tool_by_name(copied_tool_call["name"])
            if tool is None:
                state.messages.append(ToolMessage(
                    content="工具不存在",
                    tool_call_id=copied_tool_call.get("id"),
                ))
            if tool.is_parallelizable:
                # 可并行工具：创建异步任务
                task = asyncio.create_task(
                    tool.ainvoke(copied_tool_call)
                )
                parallelizable_tasks.append((copied_tool_call, task))
            else:
                # 不可并行工具：保持串行
                sequential_tools.append((copied_tool_call, tool))

        # 串行执行不可并行工具
        for tool_call, tool in sequential_tools:
            # 判断是否有Event.INTERRUPT事件，如果有则为剩下的tool_call返回用户中断执行状态，并立即返回中断执行
            if self._user_canceled:
                # 添加中断消息
                tool_result = ToolMessage(
                    content=f"用户中断执行",
                    tool_call_id=tool_call.get("id"),
                )
            else:
                try:
                    tool_result = await tool.ainvoke(tool_call)
                except GraphInterrupt:
                    raise
                except Exception as e:
                    # 处理单个工具执行失败
                    tool_result = ToolMessage(
                        content=f"工具执行失败: {str(e)}",
                        tool_call_id=tool_call.get("id"),
                    )
                    agent_logger.error("工具执行失败", exception=e)
            state.messages.append(tool_result)

        # 并行执行可并行工具
        if parallelizable_tasks:
            # 如果中断了，为所有任务发送取消执行
            if self._user_canceled:
                for tool_call, task in parallelizable_tasks:
                    # 已经执行完成的
                    if task.done():
                        if task.cancelled():
                            state.messages.append(ToolMessage(
                                content="用户中断执行",
                                tool_call_id=tool_call.get("id"),
                            ))
                        elif task.exception() is not None:
                            state.messages.append(ToolMessage(
                                content=f"执行异常: {str(task.exception())}",
                                tool_call_id=tool_call.get("id"),
                            ))
                        else:
                            state.messages.append(task.result())
                    else:
                        # 取消任务
                        task.cancel()
                        state.messages.append(ToolMessage(
                            content="用户中断执行",
                            tool_call_id=tool_call.get("id"),
                        ))
            else:
                # 等待并行执行的结果
                parallel_results = await asyncio.gather(
                    *[task for _, task in parallelizable_tasks],
                    return_exceptions=True
                )

                # 处理并行执行结果
                for (tool_call, _), result in zip(parallelizable_tasks, parallel_results):
                    if isinstance(result, GraphInterrupt):
                        raise result
                    elif isinstance(result, Exception):
                        # 处理执行异常
                        error_result = ToolMessage(
                            content=f"工具执行失败: {str(result)}",
                            tool_call_id=tool_call.get("id"),
                        )
                        agent_logger.error("工具执行失败", exception=result)
                        state.messages.append(error_result)
                    else:
                        # 正常结果
                        state.messages.append(result)

        return {
            "user_canceled": self._user_canceled,
            "messages": state.messages,
        }

    def _process_interrupt_when_tool_execute(self, interrupted: bool, state: SubAgentState) -> bool:
        """在工具执行的过程中，检测是否有用于中断行为,
        如果有中断则将未完成的tool自动失败，并将ToolMessage添加到state中

        Args:
            state (SubAgentState): 图状态，用于获取需要处理的所有工具列表以及已经处理的工具列表

        Returns:
            bool: 是否中断了
        """
        # 如果中断才处理
        if interrupted:
            tool_calls = state.tool_calls
            tool_messages = []
            for tool_call in tool_calls:
                tool_call_id = tool_call.get("id")
                processed = False
                for i in range(len(state.messages) - 1, -1, -1):
                    message = state.messages[i]
                    if isinstance(message, ToolMessage) and message.tool_call_id == tool_call_id:
                        processed = True
                        break
                    # 如果找到了AIMessage直接break
                    if isinstance(message, AIMessage):
                        break
                if not processed:
                    tool_messages.append(ToolMessage(
                        content="用户中断执行",
                        tool_call_id=tool_call_id,
                    ))
            state.messages.extend(tool_messages)
            return True
        return False

    async def _process_user_input_pending(self, state: SubAgentState) -> list[HumanMessage]:
        """处理用户输入排队消息"""
        user_messages = []
        if self.name == MAIN_AGENT_NAME:
            user_inputs = await GlobalState.get_user_input_queue().pop_all()
            if user_inputs and len(user_inputs) > 0:
                for user_input in user_inputs:
                    user_messages.append(HumanMessage(content=user_input))
                # 发送待办消息被消费事件
                writer = get_stream_writer()
                writer({
                    "type": "user_input_consumed",
                    "source": state.agent_id,
                    "content": user_inputs
                })

        return user_messages

    def _should_continue(self, state: SubAgentState) -> Literal["continue", "end", "interrupt"]:
        """判断是否需要继续执行工具"""
        if state.user_canceled:
            return "interrupt"
        elif state.tool_calls:
            return "continue"
        else:
            return "end"

    def _should_execute_tools(self, state: SubAgentState):
        """判断是否需要执行工具"""
        if state.user_canceled:
            return "interrupt"
        elif state.tool_calls:
            result = []
            # 解析TaskTool
            task_tools = [tool for tool in state.tool_calls if tool.get("name") == 'TaskTool']
            for i, _ in enumerate(task_tools):
                result.append(f"task_node_{i}")
            # 非TaskTool任务
            none_task_tools = [tool for tool in state.tool_calls if tool.get("name") != 'TaskTool']
            if none_task_tools:
                result.append("execute")
            return result
        else:
            return "skip"

    async def run_stream(self, user_input_or_resume: Any, agent_id: str, config: Optional[Dict[str, Any]] = None):
        """
        流式运行LangGraph

        Args:
            user_input_or_resume: 用户输入
            agent_id: 初始状态
            config: 配置参数，包含thread_id等

        Yields:
            流式输出块
        """
        # 记录开始执行
        agent_logger.info(f"[AGENT_START] Agent: {agent_id}, config: {config}, 输入: {user_input_or_resume}")

        # 每次运行重置中断标记
        self._user_canceled = False
        state = SubAgentState()
        # 设置agent_id
        state.agent_id = agent_id if agent_id else self._generate_agent_id()

        stream = None
        # 获取thread_id
        thread_id = (config.get("configurable", {}) if config else {}).get("thread_id", None)
        if thread_id:
            # 获取图当前的状态
            status = await self.get_graph_status(config)
            # 有中断就resume
            if status == "Interrupted":
                self.resumed_tasks = []
                stream = self.graph.astream(Command(resume=user_input_or_resume), config=config,
                                            stream_mode=["updates", "messages", "custom"],
                                            subgraphs=True)
            elif status == "Running":
                # 有next说明图正在运行中，将消息添加到队列中，等图在适当的位置将队列中的内容读取出来传给LLM
                await GlobalState.get_user_input_queue().safe_put(user_input_or_resume)
                yield {
                    "type": "user_input_queued",
                    "source": agent_id,
                    "content": user_input_or_resume
                }
            else:
                # 没有next也没有中断，说明图运行结束了，直接重启图
                state.user_input = user_input_or_resume
                # 在消息列表中拼接当前输入
                state.messages = [HumanMessage(content=user_input_or_resume)]
                stream = self.graph.astream(state, config=config, stream_mode=["updates", "messages", "custom"],
                                            subgraphs=True)
        else:
            # 没有thread_id，运行子图
            state.user_input = user_input_or_resume
            # 在消息列表中拼接当前输入
            state.messages = [HumanMessage(content=user_input_or_resume)]
            stream = self.graph.astream(state, config=config, stream_mode=["updates", "messages", "custom"],
                                        subgraphs=True)
        if stream:
            token_count = 0.0
            async for stream_data in stream:
                # agent_logger.debug(f"[STREAM DATA] {stream_data}")
                path, stream_mode, chunk = stream_data
                # 处理messages流输出 - 来自reason节点的模型实时输出
                if stream_mode == "messages":
                    # 只展示主图的消息
                    if path != ():
                        continue
                    token: AIMessageChunk
                    metadata: dict
                    token, metadata = chunk
                    # 压缩日志不显示到交互界面
                    if "tags" in metadata and any(tag in ["compact"] for tag in metadata.get("tags")):
                        continue
                    if isinstance(token, AIMessageChunk):
                        content = token.content
                        usage = token.usage_metadata
                        if content is None or content == "":
                            if not usage:
                                # 有时候模型不返回content，只返回ToolCall，这时候不是start消息，不需要向前端写东西了
                                if not token.tool_call_chunks:
                                    # 开始消息
                                    yield {
                                        "type": "message_start",
                                        "source": agent_id,
                                        "message_id": token.id,
                                    }
                                else:
                                    # 工具调用也发送消息
                                    # 预估token数量
                                    token_count += estimate_token_for_chunk_message(token)
                                    yield {
                                        "type": "message_delta",
                                        "source": agent_id,
                                        "message_id": token.id,
                                        "delta": "",
                                        "estimate_tokens": int(token_count)
                                    }

                            else:
                                # 清空
                                token_count = 0
                                # 结束消息
                                yield {
                                    "type": "message_end",
                                    "source": agent_id,
                                    "message_id": token.id,
                                }
                        else:
                            # 预估token数量
                            token_count += estimate_token_for_chunk_message(token)
                            # 消息
                            yield {
                                "type": "message_delta",
                                "source": agent_id,
                                "message_id": token.id,
                                "delta": content,
                                "estimate_tokens": int(token_count)
                            }


                # 处理updates流输出 - 节点状态更新
                elif stream_mode == "updates":
                    # chunk的结构通常是 (node_name, update_dict)
                    for node_name, data in chunk.items():
                        # 将最后一条ai消息写出去，在ToolTask中需要使用最后一条总结性消息
                        if node_name == "reason":
                            if data.get("messages"):
                                if isinstance(data.get("messages"), AIMessage):
                                    yield {
                                        "type": "last_ai_message",
                                        "source": agent_id,
                                        "message": data.get("messages")
                                    }
                                if isinstance(data.get("messages"), list) and len(
                                        data.get("messages")) > 0:
                                    yield {
                                        "type": "last_ai_message",
                                        "source": agent_id,
                                        "message": data.get("messages")[-1]
                                    }

                        # 处理interrupt节点的输出
                        if node_name == "__interrupt__":
                            # 中断会冒泡，只处理主图的中断
                            if path != ():
                                continue
                            # interrupt节点会包含权限请求信息
                            for itrpt in data:
                                interrupt_info = itrpt.value
                                interrupt_info.update({
                                    "_interrupt_id_": itrpt.id
                                })
                                yield {
                                    "type": interrupt_info.get("type", "permission_request"),
                                    "_is_interrupt_": True,
                                    "source": agent_id,
                                    "interrupt_info": interrupt_info
                                }

                # 处理custom流输出 - 来自工具的自定义流式输出
                elif stream_mode == "custom":
                    # 处理工具开始执行的消息
                    yield chunk

    async def get_graph_status(self, config) -> str:
        """获取当前图的执行状态"""
        if self.graph:
            snapshot = await self.graph.aget_state(config)
            if snapshot and snapshot.interrupts:
                return "Interrupted"
            elif snapshot and snapshot.next:
                return "Running"
        return "Finished"

    async def graph_is_running(self, config) -> bool:
        """判断指定图的状态，是否还正在运行"""
        return (await self.get_graph_status(config)) == "Running"

    async def graph_is_interrupted(self, config) -> bool:
        """判断指定图的状态，是否中断"""
        return (await self.get_graph_status(config)) == "Interrupted"
