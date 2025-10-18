"""
SubAgentGraph - 基于LangGraph的ReAct结构子代理图
"""

import asyncio
from typing import Dict, Any, List, Optional, Literal
import time

from langgraph.config import get_stream_writer
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessageChunk
from langchain_core.tools import BaseTool
from langgraph.types import Command, Interrupt, interrupt

from .event_manager import event_manager, Event, EventType
from .global_state import GlobalState
from ..constants.product import MAIN_AGENT_NAME
from ..models.state import AgentState
from ai_dev.models.model_manager import ModelManager
from ai_dev.permission.permission_manager import PermissionManager, PermissionDecision, UserPermissionChoice
from ..utils.logger import agent_logger


class SubAgentState(AgentState):
    """SubAgent专用状态类"""
    tool_calls: List[Dict[str, Any]] = []
    current_iteration: int = 0
    agent_id: Optional[str] = None
    user_interrupted: bool = False


class ReActAgent:
    """基于LangGraph的ReAct结构子代理图"""

    def __init__(
            self,
            system_prompt: list[str],
            tools: List[BaseTool],
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
        self.system_prompt = system_prompt
        self.context = context or {}

        # 初始化工具列表
        self.tools = tools

        # 初始化模型管理器
        self.model_manager = ModelManager()
        self.model_name = model or self.model_manager.default_model

        self.model = self.model_manager.get_model(self.model_name)

        self.bound_model = self.model.bind_tools(self.tools)

        # 初始化权限管理器
        self.permission_manager = PermissionManager()

        # 构建LangGraph
        self.graph = self._build_graph()

        # 订阅用户中断请求
        self._interrupted = False
        event_manager.subscribe(EventType.INTERRUPT, self._process_interrupted)

    def _process_interrupted(self, event):
        self._interrupted = True

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
        workflow.add_node("execute_tools", self._execute_tools_node)

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
                "skip": "reason",
                "interrupt": END
            }
        )

        # 工具执行完始终流转到LLM
        workflow.add_edge("execute_tools", "reason")

        # 编译图并添加中断支持
        from langgraph.checkpoint.memory import InMemorySaver
        memory = InMemorySaver()

        return workflow.compile(
            checkpointer=memory
        )

    async def _reason_node(self, state: SubAgentState):
        """推理节点 - 分析用户需求并决定下一步行动"""

        # 如果第一条不是系统消息，拼接上系统消息
        if state.messages and state.messages[0] and not isinstance(state.messages[0], SystemMessage):
            state.messages = [self._build_system_message(), *state.messages]

        # 流式获取模型响应 - 使用绑定了工具的模型
        response_content = ""
        full_message = None

        # 调用模型前，如果有用户pending，拼接进去
        new_user_inputs = await self._process_user_input_pending(state)
        if new_user_inputs:
            state.messages.extend(new_user_inputs)

        # 调用模型之前判断是否有Event.INTERRUPT事件，如果有则返回退出标记
        if self._interrupted:
            return {
                "user_interrupted": True,
            }

        # # 流式处理模型响应
        # async for chunk in self.bound_model.astream(state.messages):
        #     # 处理文本内容 - 实时产生消息流输出
        #     if chunk.content:
        #         response_content += chunk.content
        #
        #     # 拼接完成AI消息
        #     if full_message is None:
        #         full_message = chunk
        #     else:
        #         full_message = full_message + chunk
        #
        #     # 判断是否有Event.INTERRUPT事件，如果有则中断输出，直接退出
        #     if self._interrupted:
        #         return {
        #             "user_interrupted": True,
        #         }
        #
        full_message = await self.bound_model.ainvoke(state.messages)

        return {
            "tool_calls": full_message.tool_calls,
            "messages": [*state.messages, full_message],
            "current_iteration": state.current_iteration + 1
        }

    async def _check_permissions_node(self, state: SubAgentState):
        """权限检查节点 - 检查工具执行权限"""
        if not state.tool_calls:
            agent_logger.debug(f"[PERMISSION_DEBUG] Agent {state.agent_id} 没有工具调用需要检查权限")
            return {
                "tool_calls": [],
            }

        agent_logger.debug(
            f"[PERMISSION_DEBUG] Agent {state.agent_id} 开始检查 {len(state.tool_calls)} 个工具调用的权限")

        # 检查每个工具调用的权限
        allowed_tool_calls = []
        denied_tool_calls = []
        ask_requests = []  # 存储需要问询的(工具调用, 权限请求)对

        for tool_call in state.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})

            # 检查权限
            decision, request = await self.permission_manager.check_permission(tool_name, tool_args,
                                                                         GlobalState.get_working_directory())

            if decision == PermissionDecision.ALLOW:
                agent_logger.debug(f"[PERMISSION_DEBUG] Agent {state.agent_id} 工具 {tool_name} 被允许执行")
                allowed_tool_calls.append(tool_call)
            elif decision == PermissionDecision.DENY:
                agent_logger.debug(f"[PERMISSION_DEBUG] Agent {state.agent_id} 工具 {tool_name} 被拒绝执行")
                denied_tool_calls.append(tool_call)
                # 添加拒绝消息
                error_message = ToolMessage(
                    content=f"权限被拒绝: {tool_name}",
                    tool_call_id=tool_call.get("id"),
                )
                state.messages.append(error_message)
            elif decision == PermissionDecision.ASK:
                agent_logger.debug(f"[PERMISSION_DEBUG] Agent {state.agent_id} 工具 {tool_name} 需要用户确认")
                ask_requests.append((tool_call, request))

        # 如果有需要询问的工具调用，循环处理每个ASK请求
        user_refuse = False
        for tool_call, request in ask_requests:
            # 如果用户没有拒绝过，则循环请求用户授权
            if not user_refuse:
                interrupt_info = request.get_display_info()
                agent_logger.debug(f"[PERMISSION_DEBUG] Agent {state.agent_id} 向用户请求权限确认: {interrupt_info}")

                # 触发中断，等待用户选择
                user_choice = interrupt(interrupt_info)

                # 映射用户选择
                if user_choice == "1":
                    choice = UserPermissionChoice.ALLOW_ONCE
                    agent_logger.debug(f"[PERMISSION_DEBUG] Agent {state.agent_id} 用户选择: 仅本次允许")
                elif user_choice == "2":
                    choice = UserPermissionChoice.ALLOW_SESSION
                    agent_logger.debug(f"[PERMISSION_DEBUG] Agent {state.agent_id} 用户选择: 本次会话允许")
                else:
                    choice = UserPermissionChoice.DENY
                    agent_logger.debug(f"[PERMISSION_DEBUG] Agent {state.agent_id} 用户选择: 拒绝")
            else:
                # 如果用户拒绝过一个，则整个流程结束，下面所有的权限请求直接标记为拒绝
                choice = UserPermissionChoice.DENY

            # 应用用户选择并决定是否允许执行
            is_allowed = self.permission_manager.apply_user_choice(request, choice)
            if is_allowed:
                agent_logger.debug(
                    f"[PERMISSION_DEBUG] Agent {state.agent_id} 工具 {tool_call['name']} 用户确认允许执行")
                allowed_tool_calls.append(tool_call)
            else:
                user_refuse = True
                agent_logger.debug(
                    f"[PERMISSION_DEBUG] Agent {state.agent_id} 工具 {tool_call['name']} 用户确认拒绝执行")
                denied_tool_calls.append(tool_call)
                error_message = ToolMessage(
                    content=f"权限被拒绝: {tool_call['name']}",
                    tool_call_id=tool_call.get("id"),
                )
                state.messages.append(error_message)
        if user_refuse:
            # 返回用户拒绝,结束图的执行
            return {
                "user_interrupted": True,
                "messages": state.messages
            }


        agent_logger.debug(
            f"[PERMISSION_DEBUG] Agent {state.agent_id} 权限检查完成: {len(allowed_tool_calls)} 个允许, {len(denied_tool_calls)} 个拒绝")

        return {
            "tool_calls": allowed_tool_calls,
            "messages": state.messages
        }

    async def _execute_tools_node(self, state: SubAgentState):
        """异步执行工具节点 - 智能并行执行"""
        # 分类工具调用
        parallelizable_tasks = []
        sequential_tools = []

        # 判断是否有Event.INTERRUPT事件，如果有则为所有tool_call返回用户中断执行状态，并立即返回中断执行，
        #  虽然后续暂时不再执行模型调用，但是历史消息也必须要保证ToolCall请求返回ToolMessage
        if self._interrupted:
            for tool_call in state.tool_calls:
                # 添加中断消息
                error_message = ToolMessage(
                    content=f"用户中断执行",
                    tool_call_id=tool_call.get("id"),
                )
                state.messages.append(error_message)

            return {
                "user_interrupted": True,
                "messages": state.messages
            }

        for tool_call in state.tool_calls:
            # 手动弄一些参数进去
            args = tool_call.setdefault("args", {})
            args["context"] = {
                "agent_id": state.agent_id,
                "tool_id": tool_call.get("id"),
            }
            tool = {tool.name: tool for tool in self.tools}[tool_call["name"]]
            if tool.is_parallelizable:
                # 可并行工具：创建异步任务
                task = asyncio.create_task(
                    tool.ainvoke(tool_call)
                )
                parallelizable_tasks.append((tool_call, task))
            else:
                # 不可并行工具：保持串行
                sequential_tools.append((tool_call, tool))

        # 并行执行可并行工具
        if parallelizable_tasks:
            parallel_results = await asyncio.gather(
                *[task for _, task in parallelizable_tasks],
                return_exceptions=True
            )

            # 处理并行执行结果
            for (tool_call, _), result in zip(parallelizable_tasks, parallel_results):
                if isinstance(result, Exception):
                    # 处理执行异常
                    error_result = ToolMessage(
                        content=f"工具执行失败: {str(result)}",
                        tool_call_id=tool_call.get("id"),
                    )
                    state.messages.append(error_result)
                else:
                    # 正常结果
                    state.messages.append(result)

        # 串行执行不可并行工具
        for tool_call, tool in sequential_tools:
            # 判断是否有Event.INTERRUPT事件，如果有则为剩下的tool_call返回用户中断执行状态，并立即返回中断执行
            if self._interrupted:
                # 添加中断消息
                error_message = ToolMessage(
                    content=f"用户中断执行",
                    tool_call_id=tool_call.get("id"),
                )
                state.messages.append(error_message)
            else:
                try:
                    tool_result = await tool.ainvoke(tool_call)
                    state.messages.append(tool_result)
                except Exception as e:
                    # 处理单个工具执行失败
                    error_result = ToolMessage(
                        content=f"工具执行失败: {str(e)}",
                        tool_call_id=tool_call.get("id"),
                    )
                    state.messages.append(error_result)

        return {
            "user_interrupted": self._interrupted,
            "messages": state.messages,
            "tool_calls": []  # 清空工具调用列表
        }

    async def _process_user_input_pending(self, state: SubAgentState) -> list[HumanMessage]:
        """处理用户输入排队消息"""
        user_messages = []
        if state.agent_id == MAIN_AGENT_NAME:
            user_inputs = await GlobalState.get_user_input_queue().pop_all()
            if user_inputs and len(user_inputs) > 0:
                for user_input in user_inputs:
                    user_messages.append(HumanMessage(content=user_input))
                # 发送待办消息被消费事件
                writer = get_stream_writer()
                writer({
                    "type": "user_input_consumed",
                    "content": user_inputs
                })

        return user_messages

    def _should_continue(self, state: SubAgentState) -> Literal["continue", "end", "interrupt"]:
        """判断是否需要继续执行工具"""
        if state.user_interrupted:
            return "interrupt"
        elif state.tool_calls:
            return "continue"
        else:
            return "end"

    def _should_execute_tools(self, state: SubAgentState) -> Literal["execute", "skip", "interrupt"]:
        """判断是否需要执行工具"""
        if state.user_interrupted:
            return "interrupt"
        elif state.tool_calls:
            return "execute"
        else:
            return "skip"

    async def run_stream(self, user_input: str, config: Optional[Dict[str, Any]] = None):
        """
        流式运行LangGraph

        Args:
            user_input: 用户输入
            state: 初始状态
            config: 配置参数，包含thread_id等

        Yields:
            流式输出块
        """
        # 每次运行重置中断标记
        self._interrupted = False
        state = SubAgentState()
        # 设置agent_id
        agent_id = (config.get("configurable") if config else {}).get("agent_id", None)
        thread_id = (config.get("configurable") if config else {}).get("thread_id", None)
        state.agent_id = agent_id if agent_id else self._generate_agent_id()

        # 记录开始执行
        agent_logger.info(f"[AGENT_START] Agent: {state.agent_id}, thread_id: {thread_id}, 输入: {user_input}")


        stream = None
        # 获取图当前的状态
        status = await self.get_graph_status(config)
        # 有中断就resume
        if status == "Interrupted":
            stream = self.graph.astream(Command(resume=user_input), config=config,
                                    stream_mode=["updates", "messages", "custom"])
        elif status == "Running":
            # 有next说明图正在运行中，将消息添加到队列中，等图在适当的位置将队列中的内容读取出来传给LLM
            await GlobalState.get_user_input_queue().safe_put(user_input)
            yield {
                "type": "user_input_queued",
                "content": user_input
            }
        else:
            # 没有next也没有中断，说明图运行结束了，直接重启图
            state.user_input = user_input
            # 在消息列表中拼接当前输入
            state.messages = [HumanMessage(content=user_input)]
            stream = self.graph.astream(state, config=config, stream_mode=["updates", "messages", "custom"])
        if stream:
            full_response = None
            async for stream_mode, chunk in stream:
                # 处理messages流输出 - 来自reason节点的模型实时输出
                if stream_mode == "messages":
                    token: AIMessageChunk
                    metadata: dict
                    token, metadata = chunk
                    if isinstance(token, AIMessageChunk):
                        if full_response:
                            full_response += token
                        else:
                            full_response = token

                        content = token.content
                        usage = token.usage_metadata
                        if content is None or content == "":
                            if not usage:
                                # 有时候模型不返回content，只返回ToolCall，这时候不是start消息，不需要向前端写东西了
                                if not token.additional_kwargs:
                                    agent_logger.debug(f"token: {token}")
                                    # 开始消息
                                    yield {
                                        "type": "message_start",
                                        "message_id": token.id,
                                    }
                            else:
                                # 记录模型响应信息
                                agent_logger.log_model_response(state.agent_id, self.model_name, full_response)
                                # 结束消息
                                yield {
                                    "type": "message_stop",
                                    "message_id": token.id,
                                }
                        else:
                            # 消息
                            yield {
                                "type": "message_delta",
                                "message_id": token.id,
                                "delta": content,
                            }


                # 处理updates流输出 - 节点状态更新
                elif stream_mode == "updates":
                    # chunk的结构通常是 (node_name, update_dict)
                    for node_name, update_dict in chunk.items():
                        # 处理interrupt节点的输出
                        if node_name == "__interrupt__":
                            # interrupt节点会包含权限请求信息
                            if isinstance(update_dict, tuple) and len(update_dict) > 0 and isinstance(update_dict[0],
                                                                                                      Interrupt):
                                interrupt_info = update_dict[0].value
                                yield {
                                    "type": interrupt_info.get("type", "permission_request"),
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
