"""
基于prompt_toolkit的高级CLI实现
完全替换原有的rich框架实现
"""

import os
import sys
import asyncio
import uuid

import click
from typing import  List, Tuple

from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit, Window, BufferControl, Dimension
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML, FormattedText, merge_formatted_text
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.application import get_app
from prompt_toolkit.styles import Style
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.keys import Keys

from ai_dev.components.scrollable_formatted_text_control import ScrollableFormattedTextControl
from ai_dev.utils.render import process_tool_result, format_ai_output, format_patch_output, \
    format_base_execute_tool_output, format_todo_list
from ..core.assistant import AIProgrammingAssistant
from ..core.global_state import GlobalState
from ..core.config_manager import ConfigManager
from ..core.interruption_manager import InterruptionManager
from ..commands import CommandRegistry
from ..commands.clear import ClearCommand
from ..commands.agents import AgentsCommand
from ..commands.help import HelpCommand
from ..utils.logger import agent_logger
from ..components.output_capture import OutputCapture
from ai_dev.constants.product import MAIN_AGENT_NAME

class AdvancedCLI:
    """基于prompt_toolkit的高级CLI"""

    def __init__(self, working_directory: str = "."):
        # 继承原有CLI的配置和状态
        self.working_directory = working_directory
        self.assistant = None
        self.command_registry = None
        self.interruption_manager = None
        self.thread_id = None

        # 输出捕获器（新方案）
        self.output_capture = OutputCapture(self)

        # prompt_toolkit核心组件
        # 输出区域内容及显示一行数
        self.output_lines: List[Tuple[str, str]] = []  # (kind, text)
        # 输入内容
        self.input_buffer = Buffer(
            multiline=False
        )
        # 权限选择展示内容及行数控制
        self.show_choice: bool = False
        self.choice_content: FormattedText | None = None
        self.choice_options: list = []
        self.current_choice_index: int = 0
        self.actual_choice_line_count: int = 0
        self.choice_control = None

        # 待办展示内容
        self.todo_control = None
        self.todo_content: list = []
        self.show_todo: bool = False

        # 布局组件
        self.output_window = None
        self.todo_window = None
        self.up_separate_window = Window(height=1, char='─', style='class:separator')
        self.input_window = None
        self.down_separate_window = Window(height=1, char='─', style='class:separator')
        self.choice_window = None

        # 输出处理定时器
        self._output_timer_running = False

        # 按键绑定
        self.normal_kb = KeyBindings()
        self.choice_kb = KeyBindings()

        # 初始化组件
        self._initialize_components()
        self._setup_keybindings()

    def _initialize_components(self):
        """初始化prompt_toolkit组件"""
        # 输出控制
        self.output_control = ScrollableFormattedTextControl(
            self._get_output_text,
            focusable=True,
        )

        # 输入控制
        self.input_control = BufferControl(
            buffer=self.input_buffer,
            focusable=True,
            input_processors=[
                BeforeInput("> ", style="class:user")
            ]
        )

    def _setup_keybindings(self):
        """设置按键绑定"""
        # 正常模式按键绑定
        @self.normal_kb.add(Keys.ControlC)
        def exit_(event):
            """Ctrl+C 退出"""
            event.app.exit()

        @self.normal_kb.add(Keys.Enter)
        def handle_enter(event):
            """处理回车键"""
            text = self.input_buffer.text.strip()
            if not text:
                return

            # 清空输入框
            self.input_buffer.text = ""

            # 重置自动滚动状态
            self.output_control.auto_scroll = True

            # 显示用户输入
            self.add_output("user", f"\n> {text}\n")

            # 调度异步任务
            asyncio.create_task(self._handle_normal_input(text))

        # 滚动快捷键
        @self.normal_kb.add(Keys.Up)
        def scroll_up(event):
            if self.output_control.scroll_up():
                event.app.invalidate()

        @self.normal_kb.add(Keys.Down)
        def scroll_down(event):
            if self.output_control.scroll_down():
                event.app.invalidate()

        # 选择模式按键绑定
        @self.choice_kb.add('1')
        @self.choice_kb.add('2')
        @self.choice_kb.add('3')
        def handle_choice_key(event):
            key = event.key_sequence[0].key
            asyncio.create_task(self._handle_choice_input(key))

        @self.choice_kb.add(Keys.Escape)
        def handle_escape(event):
            asyncio.create_task(self._handle_choice_input("3"))

        @self.choice_kb.add(Keys.Up)
        def handle_choice_up(event):
            # 优先滚动
            if self.choice_control and self.choice_control.scroll_up():
                event.app.invalidate()
            # 无法滚动了调整选项
            elif self.current_choice_index > 0:
                self.current_choice_index -= 1
                event.app.invalidate()

        @self.choice_kb.add(Keys.Down)
        def handle_choice_down(event):
            if self.choice_control and self.choice_control.scroll_down():
                event.app.invalidate()
            elif self.current_choice_index < len(self.choice_options) - 1:
                self.current_choice_index += 1
                event.app.invalidate()

        @self.choice_kb.add(Keys.Enter)
        def handle_choice_enter(event):
            asyncio.create_task(self._handle_choice_input(str(self.current_choice_index + 1)))


    def _initialize_legacy_components(self):
        """初始化原有组件"""
        try:
            # 初始化日志系统
            agent_logger.initialize(working_directory=self.working_directory)

            # 初始化全局状态
            GlobalState.initialize(self.working_directory)
            GlobalState.set_cli_instance(self)

            # 初始化全局配置管理器
            config_manager = ConfigManager(self.working_directory)
            GlobalState.set_config_manager(config_manager)

            # 初始化命令注册表
            self.command_registry = self._initialize_command_registry()

            # 初始化中断管理器
            self.interruption_manager = InterruptionManager()

            # 初始化助手
            self.assistant = AIProgrammingAssistant(
                working_directory=self.working_directory,
            )

            self.thread_id = str(uuid.uuid4())

            agent_logger.info("AdvancedCLI初始化完成")
            return True
        except Exception as e:
            self.add_output("error", f"初始化失败: {e}")
            agent_logger.log_agent_error("advanced_cli_init", str(e), e, {
                "working_directory": self.working_directory,
                "stage": "initialization"
            })
            return False

    def _initialize_command_registry(self) -> CommandRegistry:
        """初始化指令注册表"""
        registry = CommandRegistry()
        registry.register("clear", ClearCommand)
        registry.register("agents", AgentsCommand)
        registry.register("help", HelpCommand)
        return registry

    def _get_output_text(self):
        """获取输出文本"""
        parts = []
        for kind, text in self.output_lines:
            if kind == "user":
                parts.append(FormattedText([('class:user', text + "\n")]))
            elif kind == "ai":
                # 不要展开 ANSI！
                parts.append(format_ai_output(text))  # 返回 ANSI 对象
            elif kind == "error":
                parts.append(FormattedText([('class:error', text + "\n")]))
            elif kind == "warning":
                parts.append(FormattedText([('class:warning', text + "\n")]))
            elif kind == "info":
                parts.append(FormattedText([('class:info', text + "\n")]))
            elif kind in ["tool_title", "tool_result", "tool_error"]:
                parts.append(HTML(text + "\n"))
            elif kind == "tool_patch":
                parts.append(format_patch_output(text))
            elif kind == "base_execute_result":
                parts.append(format_base_execute_tool_output(text))
            else:
                parts.append(FormattedText([('', text + "\n")]))
        return merge_formatted_text(parts)

    def _get_choice_text(self):
        parts = []
        parts.append(self.choice_content)
        for index, option in enumerate(self.choice_options):
            if index == self.current_choice_index:
                parts.append(FormattedText([('class:common.blue', "  > " + option + "\n")]))
            else:
                parts.append(FormattedText([("", "    " + option + "\n")]))
        return merge_formatted_text(parts)

    def _get_todo_text(self):
        return format_todo_list(self.todo_content)

    def set_todo_list(self, todos: list):
        if todos and len(todos) > 0:
            self.todo_content = todos
            self.create_todo_window()
            self.show_todo = True
        else:
            self.todo_content = []
            self.show_todo = False
        self.re_construct_layout()

    def add_output(self, kind: str, text: str, append: bool = False):
        """添加输出行"""
        if append and self.output_lines and self.output_lines[-1][0] == kind:
            self.output_lines[-1] = (kind, self.output_lines[-1][1] + text)
        else:
            self.output_lines.append((kind, text))

        self.refresh()

        # 立即强制重绘，确保内容显示并滚动
        try:
            app = get_app()
            app.invalidate()
        except:
            pass

    def add_outputs(self, kind: str, texts: List[str]):
        """添加多个输出行"""
        for text in texts:
            self.add_output(kind, text)

    def refresh(self):
        """更新输出显示"""
        try:
            app = get_app()
            app.invalidate()
        except:
            # 应用尚未创建，忽略错误
            pass

    async def _output_processing_loop(self):
        """输出处理循环 - 定期检查捕获的输出"""
        self._output_timer_running = True

        try:
            while self._output_timer_running:
                # 处理捕获的输出
                captured_items = self.output_capture.process_captured_output()

                for item in captured_items:
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
                        self.add_output("error", f"❌ {error_msg}")
                        self.add_output("info", "详细信息请查看日志文件")
                        # 记录完整堆栈到日志
                        agent_logger.error(f"[Captured Exception]\n{stack_trace}")

                # 等待一小段时间
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        finally:
            self._output_timer_running = False

    def get_output_window(self):
        """获取输出窗口"""
        if self.output_window is None:
            self.output_window = Window(
                content=self.output_control,
                wrap_lines=True,
                always_hide_cursor=True,
                height=None
            )
        return self.output_window

    def get_input_window(self):
        """获取输入窗口"""
        if self.input_window is None:
            self.input_window = Window(content=self.input_control, height=1)
        return self.input_window

    def create_choice_window(self):
        # 权限选择控制
        self.choice_control = ScrollableFormattedTextControl(
            self._get_choice_text,
            focusable=True,
        )
        self.choice_window = Window(
            content=self.choice_control,
            # height=Dimension(preferred=self.actual_choice_line_count)
        )
        return self.choice_window

    def create_todo_window(self):
        # 待办列表控制器
        self.todo_control = ScrollableFormattedTextControl(
            self._get_todo_text,
            focusable=True,
        )
        self.todo_window = Window(
            content=self.todo_control
        )
        return self.todo_window

    def create_layout(self):
        """创建布局"""
        return Layout(
            HSplit([
                # 输出区域（自动扩展）
                self.get_output_window(),
                # 分隔线
                self.up_separate_window,
                # 输入框或选择框（固定高度）
                self.get_input_window(),
                # 分隔线
                self.down_separate_window,
            ]),
            focused_element=self.input_window,
        )

    async def _handle_normal_input(self, text: str):
        """处理正常输入"""
        # 处理退出指令
        if text.lower() in ["quit", "exit", "q"]:
            get_app().exit()
            return

        # 处理指令
        if self.command_registry and self.command_registry.is_command(text):
            self._handle_slash_command(text)
            return

        # 流式处理自然语言输入
        await self._process_stream_input(text)

    async def _handle_choice_input(self, choice: str):
        """处理选择输入"""
        if choice not in ['1', '2', '3']:
            self.add_output("error", "❌ 请输入 1、2 或 3")
            return

        # 恢复输入框
        self.show_choice=False
        self.re_construct_layout()

        # 处理选择结果
        await self._handle_interruption_recovery(choice)

    async def _handle_interruption_recovery(self, recovery_input: str):
        """处理中断恢复"""
        try:
            agent_logger.info(f"开始处理中断恢复: {recovery_input}")

            await self._process_stream_input(recovery_input, True)

            agent_logger.info(f"中断恢复处理完成: {recovery_input}")
        except Exception as e:
            self.add_output("error", f"中断恢复处理失败: {e}")
            agent_logger.log_agent_error("interruption_recovery", str(e), e, {
                "recovery_input": recovery_input,
                "stage": "interruption_recovery"
            })

    def _handle_slash_command(self, user_input: str) -> bool:
        """处理斜杠指令"""
        command_name, args = self.command_registry.parse_command(user_input)
        command_class = self.command_registry.get_command(command_name)

        if not command_class:
            self.add_output("error", f"未知指令: /{command_name}")
            self.add_output("info", "使用 /help 查看可用指令")
            return True

        try:
            command = command_class()
            return command.execute(self, args)
        except Exception as e:
            self.add_output("error", f"执行指令 /{command_name} 时出错: {e}")
            agent_logger.log_agent_error("slash_command", str(e), e, {
                "command": command_name,
                "args": args,
                "stage": "command_execution"
            })
            return True

    async def _process_stream_input(self, user_input: str, resume:bool=False):
        """流式处理用户输入"""
        if not self.assistant:
            self.add_output("error", "助手未初始化")
            return

        agent_logger.log_agent_start(MAIN_AGENT_NAME, user_input)

        full_response = ""
        has_interrupted = False

        try:

            async for chunk in self.assistant.process_input_stream(user_input,
                                                                   thread_id=self.thread_id,
                                                                   resume=resume):
                if self.interruption_manager.is_interruption_chunk(chunk):
                    await self.interruption_manager.handle_interruption(
                        chunk["type"], chunk["interrupt_info"]
                    )
                    has_interrupted = True

                elif chunk.get("type") == "error":
                    self.add_output("error", chunk["error"])
                    agent_logger.log_agent_error(MAIN_AGENT_NAME, chunk["error"], None, {
                        "stage": "stream_processing"
                    })

                elif chunk.get("type") == "text_chunk":
                    full_response = chunk["full_response"]
                    content = chunk["content"]
                    self.add_output("ai", content, append=True)

                elif chunk.get("type") == "llm_finish":
                    pass

                elif chunk.get("type") == "tool_start":
                    message = chunk.get("title", "调用工具")
                    self.add_output("tool_title", f"\n {message}")

                elif chunk.get("type") == "tool_progress":
                    message = chunk.get("message", "")
                    self.add_output("info", f"🛠️ {message}")

                elif chunk.get("type") == "tool_complete":
                    for item in await process_tool_result(chunk):
                        if item[0] == 'output':
                            self.add_output(item[1], item[2])
                        elif item[0] == 'todo':
                            self.set_todo_list(item[2])


                elif chunk.get("type") == "custom":
                    content = chunk.get("content", "")
                    self.add_output("info", f"📌 {content}")

                elif chunk.get("type") == "complete":
                    full_response = chunk["full_response"]
                    agent_logger.log_agent_complete(MAIN_AGENT_NAME, full_response)

        except Exception as e:
            self.add_output("error", f"处理流时出错: {str(e)}")
            agent_logger.log_agent_error(MAIN_AGENT_NAME, str(e), e, {
                "user_input": user_input,
                "stage": "stream_processing"
            })

        if not full_response and not has_interrupted:
            self.add_output("error", "❌ 没有生成响应")
            agent_logger.log_no_response(MAIN_AGENT_NAME, "处理了但没有生成响应")

    def show_permission_request(self, choice_text: FormattedText, options: list):
        """显示权限请求选择界面"""
        # 替换原choice_window中的内容
        self.choice_content = choice_text
        self.choice_options = options
        # 每次创建独立的窗口
        self.show_choice=True
        self.create_choice_window()
        self.re_construct_layout()

    def re_construct_layout(self):
        """根据状态重新构建layout内组件"""
        app = get_app()
        new_children =[self.output_window]
        if self.show_todo:
            new_children.append(self.todo_window)
        else:
            self.todo_window = None
            self.todo_control = None
        new_children.append(self.up_separate_window)
        if self.show_choice:
            new_children.append(self.choice_window)
            self.input_buffer.read_only = lambda: True
            app.key_bindings = self.choice_kb
        else:
            self.choice_window = None
            self.choice_control = None
            new_children.append(self.input_window)
            self.input_buffer.read_only = lambda: False
            app.key_bindings = self.normal_kb
        new_children.append(self.down_separate_window)
        app.layout.container.children = new_children
        app.invalidate()

    def print_welcome(self):
        """打印欢迎信息"""
        welcome_texts = [
            "═" * 60,
            "  🤖 AI Programming Assistant",
            "═" * 60,
            "",
            "欢迎使用AI编程助手！我可以帮助您：",
            "• 读取和编辑文件",
            "• 搜索代码内容",
            "• 执行系统命令",
            "• 管理项目环境",
            "",
            "使用方式：",
            "• 输入自然语言问题获得AI帮助",
            "• 使用 /help 查看所有可用指令",
            "• 使用 /clear 清除对话历史",
            "• 使用 /agents 查看可用代理",
            "• 输入 'quit' 退出程序",
            ""
        ]
        self.add_outputs("info", welcome_texts)

    async def run_interactive_stream(self):
        """运行流式交互式模式"""

        # 启动输出捕获
        self.output_capture.start()

        # 启动输出处理循环
        output_task = asyncio.create_task(self._output_processing_loop())

        try:
            # 初始化原有组件
            if not self._initialize_legacy_components():
                return

            # 打印欢迎信息
            self.print_welcome()

            # 创建布局
            layout = self.create_layout()

            # 自定义样式
            style = Style.from_dict({
                'separator': '#888888',
                'user': '#dddddd bold',
                'ai': '',
                'error': '#FF6B6B bold',
                'warning': '#FFA726 bold',
                'info': '#4FC3F7',
                'common.gray': '#cccccc',
                'common.blue': '#3366FF',
                'common.red': '#FF6B6B',
                'common.purple': '#8B5CF6',
                'common.pink': '#FF1493',

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
                    key_bindings=self.normal_kb,
                    full_screen=True,
                    mouse_support=True,
                    style=style,
                    # 使用真实的终端输出（不受重定向影响）
                    output=create_output(stdout=self.output_capture.get_real_stdout()),
                    after_render=after_render
                )


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
            self.add_output("info", "感谢使用AI编程助手！")

        except KeyboardInterrupt:
            agent_logger.info("[Start] 用户中断")
        except Exception as e:
            agent_logger.error(f"[Start] 运行异常: {e}", exception=e)
            raise
        finally:
            # 停止输出处理循环
            self._output_timer_running = False
            output_task.cancel()
            try:
                await output_task
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