"""
基于prompt_toolkit的高级CLI实现
完全替换原有的rich框架实现
"""

import os
import sys
import asyncio
import uuid

import click

from typing import Any

from prompt_toolkit import Application
from prompt_toolkit.clipboard import ClipboardData
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.application import get_app
from prompt_toolkit.styles import Style
from prompt_toolkit.keys import Keys

from ai_dev.components.choice_window import ChoiceWindow
from ai_dev.components.input_window import InputWindow
from ai_dev.models.model_manager import ModelManager
from ai_dev.permission.permission_manager import PermissionManager
from ai_dev.utils.mcp import mcp_client
from ai_dev.utils.todo import clean_todo_files
from ..core.assistant import AIProgrammingAssistant
from ..core.global_state import GlobalState
from ..core.config_manager import ConfigManager
from ..core.event_manager import Event, EventType, event_manager
from ..commands import CommandRegistry
from ..commands.clear import ClearCommand
from ..commands.agents import AgentsCommand
from ..commands.help import HelpCommand
from ..utils.logger import agent_logger
from ..components.output_capture import OutputCapture
from ai_dev.constants.product import MAIN_AGENT_ID
from ai_dev.components.output_window import OutputWindow

class AdvancedCLI:
    """基于prompt_toolkit的高级CLI"""

    def __init__(self, working_directory: str = "."):
        # 继承原有CLI的配置和状态
        self.working_directory = working_directory
        self.assistant: AIProgrammingAssistant | None = None
        self.command_registry = None
        self.thread_id = None

        # 输出捕获器
        self.output_capture = OutputCapture(self)

        # prompt_toolkit核心组件
        self.output_window: OutputWindow | None = None
        self.choice_window: ChoiceWindow | None = None
        self.input_window: InputWindow | None = None

        # 布局组件
        self.up_separate_window = Window(height=1, char='─', style='class:separator')
        self.down_separate_window = Window(height=1, char='─', style='class:separator')

        # 输出处理定时器
        self._output_timer_running = False

        # 按键绑定
        self.normal_kb = KeyBindings()

        # 初始化组件
        self._initialize_components()
        self._setup_keybindings()
        self._initialize_legacy_components()

    def _initialize_components(self):
        """初始化prompt_toolkit组件"""
        self.output_window = OutputWindow(cli=self)
        self.choice_window = ChoiceWindow(cli=self)
        self.input_window = InputWindow(cli=self)

    def _setup_keybindings(self):
        """设置按键绑定"""
        # 正常模式按键绑定
        @self.normal_kb.add(Keys.ControlZ)
        def exit_(event):
            """Ctrl+Z 退出"""
            event.app.exit()

        # esc / Control+C中断图执行
        @self.normal_kb.add(Keys.Escape)
        @self.normal_kb.add(Keys.ControlC)
        async def handle_interrupt(event):
            """处理全局中断事件"""
            import time

            # 创建中断事件
            user_cancel_event = Event(
                event_type=EventType.USER_CANCEL,
                data={
                    "source": "keyboard",
                },
                source="AdvancedCLI",
                timestamp=time.time()
            )

            # 发布中断事件
            await event_manager.publish(user_cancel_event)
            agent_logger.info(f"全局中断事件已发布: {user_cancel_event}")

        # 复制选中内容
        @self.normal_kb.add(Keys.ControlX)
        async def handle_copy(event):
            layout = event.app.layout
            if layout.has_focus(self.output_window.window):
                self.output_window.window.content.copy_selection()
                # 复制完了重置焦点
                self.process_focus()
            elif layout.has_focus(self.choice_window.window):
                self.choice_window.window.content.copy_selection()
                self.process_focus()
            elif layout.has_focus(self.input_window.window.window):
                clipboard_data: ClipboardData = self.input_window.window.buffer.copy_selection()
                if clipboard_data and clipboard_data.text:
                    import pyperclip
                    """复制到系统剪贴板"""
                    pyperclip.copy(clipboard_data.text)

        # 切换显示模式
        @self.normal_kb.add(Keys.ControlO)
        async def change_display_mode(event):
            if GlobalState.get_show_output_details():
                GlobalState.set_show_output_details(False)
            else:
                GlobalState.set_show_output_details(True)
            event.app.invalidate()


    def _initialize_legacy_components(self):
        """初始化原有组件"""
        # 初始化日志系统
        agent_logger.initialize(working_directory=self.working_directory)

        # 初始化全局状态
        GlobalState.initialize(self.working_directory)
        GlobalState.set_cli_instance(self)

        # 初始化全局配置管理器
        config_manager = ConfigManager(self.working_directory)
        GlobalState.set_config_manager(config_manager)

        # 初始化全局模型管理器
        model_manager = ModelManager()
        GlobalState.set_model_manager(model_manager)

        # 注册全局的权限管理器
        permission_manager = PermissionManager()
        GlobalState.set_permission_manager(permission_manager)

        # 初始化命令注册表
        self.command_registry = self._initialize_command_registry()

        # 初始化助手
        self.assistant = AIProgrammingAssistant(
            working_directory=self.working_directory,
        )

        self.thread_id = str(uuid.uuid4())

        agent_logger.info("AdvancedCLI初始化完成")

    def _initialize_command_registry(self) -> CommandRegistry:
        """初始化指令注册表"""
        registry = CommandRegistry()
        registry.register("clear", ClearCommand)
        registry.register("agents", AgentsCommand)
        registry.register("help", HelpCommand)
        return registry

    async def process_user_input(self, user_input: str) -> str:
        """ 展示用户输入
        需要根据当前graph处理的状态来决定是直接展示在output_control中，还是需要展示在pending队列中

        Returns:
            str:    Quit: 退出
                    Command: 指令处理
                    Queued: 输入排队
                    Input: 出入正常处理
        """
        # 处理退出指令
        if user_input.lower() in ["quit", "exit", "q"]:
            get_app().exit()
            return 'Quit'

        # 处理指令
        if self.command_registry and self.command_registry.is_command(user_input):
            await self._handle_slash_command(user_input)
            return 'Command'

        # 其他输入
        config = {
            "configurable": {
                "thread_id": self.thread_id,
            }
        }
        agent_is_running = await self.assistant.agent_is_running(config)
        if agent_is_running:
            agent_logger.debug(f"[Pending for user input]: {user_input}")
            # 将消息添加到queue中
            await GlobalState.get_user_input_queue().safe_put(user_input)
            return 'Queued'

        # 直接显示用户输入
        await self.output_window.add_user_input_block(user_input)
        return 'Input'

    async def _output_processing_loop(self):
        """输出处理循环 - 定期检查捕获的输出"""
        self._output_timer_running = True

        try:
            while self._output_timer_running:
                # 处理捕获的输出
                for item in self.output_capture.process_captured_output():
                    if item[0] == 'captured_print':
                        # 捕获的 print 输出 - 只记录到日志，不显示在界面
                        _, kind, content = item
                        # 记录到日志系统
                        agent_logger.debug(f"[Captured Print] {content}")
                        # **不添加到界面显示**
                        # self.add_output(kind, f"📝 {content}")

                    elif item[0] == 'exception':
                        # 异常信息 - 显示在界面
                        _, error_msg, stack_trace = item
                        # 记录完整堆栈到日志
                        agent_logger.error(f"[Captured Exception]\n{stack_trace}")

                # 等待一小段时间
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        finally:
            self._output_timer_running = False

    def init_layout(self):
        """创建布局"""
        return Layout(
            HSplit([
                # 输出区域（自动扩展）
                self.output_window.window,
                # 分隔线
                self.up_separate_window,
                # 输入框或选择框（固定高度）
                self.input_window.window.window,
                # 分隔线
                self.down_separate_window,
            ]),
            focused_element=self.input_window.window.window,
        )

    async def _handle_slash_command(self, user_input: str) -> bool:
        """处理斜杠指令"""
        command_name, args = self.command_registry.parse_command(user_input)
        command_class = self.command_registry.get_command(command_name)

        if not command_class:
            await self.output_window.add_common_block("class:error", f"未知指令: /{command_name}")
            await self.output_window.add_common_block("class:info", "使用 /help 查看可用指令")
            return True

        try:
            command = command_class()
            return command.execute(self, args)
        except Exception as e:
            await self.output_window.add_common_block("class:error", f"执行指令 /{command_name} 时出错: {e}")
            agent_logger.log_agent_error("slash_command", str(e), e, {
                "command": command_name,
                "args": args,
                "stage": "command_execution"
            })
            return True

    async def process_stream_input(self, user_input_or_resume: Any, resume_task_ids: list = None) -> Any:
        """流式处理用户输入"""
        if not self.assistant:
            await self.output_window.add_common_block("class:error", "助手未初始化")
            return

        agent_logger.log_agent_start(MAIN_AGENT_ID, user_input_or_resume)

        try:

            async for chunk in self.assistant.process_input_stream(user_input_or_resume,
                                                                   thread_id=self.thread_id,
                                                                   resume_task_ids=resume_task_ids):
                # 中断
                if "_is_interrupt_" in chunk and chunk["_is_interrupt_"] == True:
                    await self.choice_window.append_interruption(chunk.get("interrupt_info"))

                # 异常
                elif chunk.get("type") == "error":
                    await self.output_window.add_common_block("class:error", chunk["error"])

                # 用户输入被排队了
                elif chunk.get("type") == "user_input_queued":
                    # 如果用户输入的时候agent没有在运行，但是实际提交的时候已经运行了，会被agent塞到队列里不执行，这时候从输出面板里删除掉
                    # 在pending面板会自动显示
                    await self.output_window.remove_recently_user_input_block(chunk["content"])

                # 用户排队的消息被消费了
                elif chunk.get("type") == "user_input_consumed":
                    # 用户pending消息被消费
                    agent_logger.debug(f"[Receive user input consumed]: {chunk['content']}")
                    await self.output_window.user_pending_input_consumed(chunk["content"])

                # 其他类型的消息
                else:
                    await self.output_window.add_stream_output(chunk)


        except Exception as e:
            await self.output_window.add_common_block("class:error", f"处理流时出错: {str(e)}")
            agent_logger.log_agent_error(MAIN_AGENT_ID, str(e), e, {
                "user_input": user_input_or_resume,
                "stage": "stream_processing"
            })

    def re_construct_layout(self):
        """根据状态重新构建layout内组件"""
        app = get_app()
        new_children =[self.output_window.window]
        # 上分割线
        new_children.append(self.up_separate_window)
        # 显示选择
        if self.choice_window.need_show():
            new_children.append(self.choice_window.window)
            self.input_window.set_buffer_editable(False)
            choice_kb = self.choice_window.get_choice_key_bindings()
            app.key_bindings = merge_key_bindings([self.normal_kb, choice_kb])
        # or 显示输入
        else:
            new_children.append(self.input_window.window.window)
            self.input_window.set_buffer_editable(True)
            input_kb = self.input_window.get_input_kb()
            app.key_bindings = merge_key_bindings([self.normal_kb, input_kb])
        # 下分割线
        new_children.append(self.down_separate_window)
        app.layout.container.children = new_children
        # 焦点处理
        self.process_focus()
        app.invalidate()

    def process_focus(self):
        # 如果当前不是选择，给输入库聚焦
        if not self.choice_window.need_show():
            get_app().layout.focus(self.input_window.window.window)
        else:
            get_app().layout.focus(self.choice_window.window)


    async def print_welcome(self):
        """打印欢迎信息"""
        welcome_texts = [
            "═" * 60,
            "  🤖 AI Programming Assistant",
            "═" * 60,
            " ",
            "欢迎使用AI编程助手！我可以帮助您：",
            "• 读取和编辑文件",
            "• 搜索代码内容",
            "• 执行系统命令",
            "• 管理项目环境",
            " ",
            "使用方式：",
            "• 输入自然语言问题获得AI帮助",
            "• 使用 /help 查看所有可用指令",
            "• 使用 /clear 清除对话历史",
            "• 使用 /agents 查看可用代理",
            "• 输入 'quit' 退出程序",
            " "
        ]
        await self.output_window.batch_add_common_block("class:info", welcome_texts)

    async def run_interactive_stream(self):
        """运行流式交互式模式"""

        # 启动事件管理器
        await event_manager.start()
        # 启动输出捕获
        self.output_capture.start()
        # 启动输出处理循环
        output_task = asyncio.create_task(self._output_processing_loop())
        # 补偿Pending消息消费循环
        compensation_pending_task = asyncio.create_task(self.output_window.compensation_pending_input_loop())
        # 开启任务执行中呼吸灯
        task_breathe_color_task = asyncio.create_task(self.output_window.task_breathe_color_controller_loop())
        # 初始化mcp client
        await mcp_client.initialize()
        # 清理历史代办列表
        clean_todo_files()

        try:

            # 打印欢迎信息
            await self.print_welcome()

            # 创建布局
            layout = self.init_layout()

            # 自定义样式
            style = Style.from_dict({
                'separator': '#888888',
                'user': '#dddddd',
                'ai': '',
                'error': '#FF6B6B bold',
                'warning': '#FFA726 bold',
                'info': '#4FC3F7',
                'common.gray': '#cccccc',
                'common.blue': '#3366FF',
                'common.red': '#FF6B6B',
                'common.purple': '#8B5CF6',
                'common.pink': '#FADBD8',

                'tool.patch.line_number': '#cccccc',
                'tool.patch.line_number.removed': '#cccccc',
                'tool.patch.line_number.added': '#cccccc',
                'tool.patch.diff.hunk_info': '#cccccc',
                'tool.patch.diff.added': '#cccccc bg:#5f875f',
                'tool.patch.diff.removed': '#cccccc bg:#875f87',
                'tool.patch.diff.context': '#ffffff',

                'permission.title': '#3366FF bold',
            })

            try:
                # 使用真实的终端输出
                from prompt_toolkit.output import create_output

                def after_render(app):
                    pass


                app = Application(
                    layout=layout,
                    key_bindings=merge_key_bindings([self.normal_kb, self.input_window.get_input_kb()]),
                    full_screen=False,
                    mouse_support=True,
                    style=style,
                    # 使用真实的终端输出（不受重定向影响）
                    output=create_output(stdout=self.output_capture.get_real_stdout()),
                    after_render=after_render
                )

                # 子组件中绑定app
                self.output_window.set_app(app)
                self.choice_window.set_app(app)
                self.input_window.set_app(app)

            except Exception as e:
                agent_logger.error(f"[Start] 应用创建失败: {e}", exception=e)
                raise

            try:
                await app.run_async()
            except Exception as e:
                agent_logger.error(f"[Start] 应用运行异常: {e}", exception=e)
                raise

            agent_logger.debug("[Start] 应用结束")

            # 清理
            await self.output_window.add_common_block("class:info", "感谢使用AI编程助手！")

        except KeyboardInterrupt:
            agent_logger.info("[Start] 用户中断")
        except Exception as e:
            agent_logger.error(f"[Start] 运行异常: {e}", exception=e)
            raise
        finally:
            # 停止事件管理器
            await event_manager.stop()

            # 停止输出处理循环
            self._output_timer_running = False
            output_task.cancel()
            try:
                await output_task
            except asyncio.CancelledError:
                pass

            # 停止pending监听
            compensation_pending_task.cancel()
            try:
                await compensation_pending_task
            except asyncio.CancelledError:
                pass

            # 停止呼吸灯
            task_breathe_color_task.cancel()
            try:
                await task_breathe_color_task
            except asyncio.CancelledError:
                pass

            # 停止输出捕获
            self.output_capture.stop()

    def run(self):
        """运行应用"""
        try:
            # 检查是否在终端环境中
            if not sys.stdout.isatty():
                agent_logger.warning(f"警告：未检测到终端环境，某些功能可能无法正常工作")

            asyncio.run(self.run_interactive_stream())
        except KeyboardInterrupt:
            agent_logger.info("\n程序已退出")
        except Exception as e:
            agent_logger.error(f"程序异常退出:", exception=e)
            import traceback
            traceback.print_exc()


@click.command()
@click.option(
    "--directory", "-d",
    default=".",
    help="工作目录 (默认: 当前目录)"
)
@click.option(
    "--model", "-m",
    default=None,
    help="使用的模型 (可选: deepseek-chat, deepseek-coder, gpt-4o, gpt-3.5-turbo)"
)
@click.option(
    "--log-dir",
    default=None,
    help="日志目录 (默认: /opt/apps/logs/ai-dev/ 或工作目录下的logs目录)"
)
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="日志级别 (默认: INFO)"
)
@click.option(
    "--debug",
    is_flag=True,
    help="启用调试模式"
)
def main(directory: str, log_dir: str, log_level: str, model: str, debug: bool):
    """AI编程助手命令行工具 - 高级版本"""

    # 设置日志配置
    if log_dir:
        os.environ["AI_DEV_LOG_DIR"] = log_dir
    if log_level:
        os.environ["AI_DEV_LOG_LEVEL"] = log_level

    # 设置默认模型配置 - 优先使用命令行参数
    if model:
        os.environ["AI_DEV_DEFAULT_MODEL"] = model

    try:
        cli = AdvancedCLI(working_directory=directory)
        cli.run()
    except Exception as e:
        agent_logger.error(f"启动失败:", exception=e)
        if debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()