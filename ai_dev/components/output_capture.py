import sys

import traceback
from queue import Queue, Empty

from ..utils.logger import agent_logger

class OutputCapture:
    """
    输出捕获器 - 使用队列机制捕获 print 和异常，不干扰 prompt_toolkit
    """

    def __init__(self, cli_instance):
        self.cli_instance = cli_instance
        self.original_stdout = None
        self.original_stderr = None
        self.capture_queue = Queue()
        self._active = False

        # 保存真实的终端流（prompt_toolkit需要）
        self._real_stdout = None
        self._real_stderr = None

    def start(self):
        """启动输出捕获"""
        if self._active:
            return

        # 保存原始流
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

        # 保存真实的终端流（用于 prompt_toolkit）
        self._real_stdout = self.original_stdout
        self._real_stderr = self.original_stderr

        # 创建捕获包装器
        sys.stdout = self._create_capture_wrapper(self.original_stdout, 'stdout')
        sys.stderr = self._create_capture_wrapper(self.original_stderr, 'stderr')

        # 设置异常处理
        sys.excepthook = self._exception_handler

        self._active = True

    def stop(self):
        """停止输出捕获"""
        if not self._active:
            return

        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        sys.excepthook = sys.__excepthook__

        self._active = False

    def _create_capture_wrapper(self, original_stream, stream_name):
        """创建捕获包装器"""
        class CaptureWrapper:
            def __init__(wrapper_self, stream, queue, stream_type, real_stream):
                wrapper_self.stream = stream
                wrapper_self.queue = queue
                wrapper_self.stream_type = stream_type
                wrapper_self.real_stream = real_stream

            def write(wrapper_self, text):
                # **关键修改：不写入真实流，只捕获到队列**
                # 这样 print 就不会显示在交互界面上

                # 捕获到队列（用于日志记录）
                if text and text.strip():
                    kind = 'warning' if wrapper_self.stream_type == 'stderr' else 'warning'
                    # 直接发送到队列，不经过缓冲区
                    wrapper_self.queue.put(('captured_print', kind, text.strip()))

                # 返回写入的字符数（模拟正常的 write 行为）
                return len(text) if text else 0

            def flush(wrapper_self):
                # 刷新缓冲区 - 现在没有缓冲区，直接返回
                pass

            def isatty(wrapper_self):
                # 返回 False，表示这不是一个终端
                # 某些库会根据这个判断是否输出彩色文本
                return False

            def fileno(wrapper_self):
                # 返回真实流的文件描述符
                try:
                    return wrapper_self.real_stream.fileno()
                except:
                    return -1

            def __getattr__(wrapper_self, name):
                # 转发其他属性到真实流
                return getattr(wrapper_self.real_stream, name)

        return CaptureWrapper(original_stream, self.capture_queue, stream_name,
                            self._real_stdout if stream_name == 'stdout' else self._real_stderr)

    def _exception_handler(self, exc_type, exc_value, exc_traceback):
        """全局异常处理器"""
        if exc_type == KeyboardInterrupt:
            # 让 KeyboardInterrupt 正常传递
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        error_msg = f"未捕获的异常: {exc_type.__name__}: {exc_value}"
        stack_trace = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))

        # 记录到日志
        try:
            agent_logger.error(error_msg, exception=exc_value,
                             context={"stage": "global_exception"})
        except:
            pass

        # 发送到队列
        self.capture_queue.put(('exception', error_msg, stack_trace))

    def get_real_stdout(self):
        """获取真实的 stdout（供 prompt_toolkit 使用）"""
        return self._real_stdout or sys.__stdout__

    def get_real_stderr(self):
        """获取真实的 stderr（供 prompt_toolkit 使用）"""
        return self._real_stderr or sys.__stderr__

    def process_captured_output(self):
        """处理捕获的输出（CLI主循环调用）"""
        try:
            while True:
                try:
                    item = self.capture_queue.get_nowait()
                    yield item
                except Empty:
                    break
        except:
            pass
