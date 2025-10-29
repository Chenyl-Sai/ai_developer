# AI Developer Assistant

基于 LangChain 和 LangGraph 构建的AI开发助手，提供类似Claude Code的交互体验。

## 功能特性

### 核心功能
- ✅ **高级CLI界面** - 基于prompt_toolkit的交互式命令行体验
- ✅ **ReAct架构** - 基于LangGraph的推理-行动循环
- ✅ **智能工具系统** - 可扩展的工具注册和权限管理
- ✅ **文件操作** - 读取、写入、编辑、列出、搜索文件
- ✅ **代码搜索** - 在项目中搜索特定内容
- ✅ **系统命令** - 安全地执行系统命令
- ✅ **任务管理** - TodoWrite工具跟踪任务进度
- ✅ **权限控制** - 细粒度的文件操作权限检查
- ✅ **流式输出** - 实时显示AI响应和工具执行进度
- ✅ **中断恢复** - 支持权限中断和用户交互恢复

### 安全特性
- 🔒 **路径验证** - 防止访问工作目录外的文件
- 🔒 **权限分级** - 自动/询问/拒绝三级权限控制
- 🔒 **会话隔离** - 不同会话间的权限状态隔离
- 🔒 **安全执行** - 工具执行异常处理和错误恢复

## 安装

### 环境要求
- Python 3.11+
- 支持的AI模型：DeepSeek Chat, GPT-4o, GPT-3.5-turbo

### 安装步骤

1. 克隆项目：
```bash
git clone <repository-url>
cd ai_developer
```

2. 安装依赖：
```bash
# 创建虚拟环境(使用conda/venv等等均可)
conda create --name ai_dev python=3.11
conda activate ai_dev
# 安装依赖
pip install -e .
```

3. 配置API密钥：
```bash
export OPENAI_API_KEY="your-openai-api-key"
# 或
export DEEPSEEK_API_KEY="your-deepseek-api-key"
```

## 使用方法

### 交互式模式
```bash
cd <youe-project-dir>
ai-dev
```

### 指定工作目录
```bash
ai-dev --directory /path/to/your/project
```

### 选择模型
```bash
ai-dev --model deepseek-chat
ai-dev --model gpt-4o
```

### 调试模式
```bash
ai-dev --debug
```

## 使用示例

```bash
# 自然语言交互
> 帮我查看当前目录的文件结构

> 搜索所有包含main函数的文件

> 创建一个新的Python文件并添加一些代码

> 帮我修复这个代码中的bug

# 内置命令
> /help - 查看所有可用命令

> /clear - 清除对话历史

> /agents - 查看可用代理

> quit - 退出程序
```

## 项目结构

```
ai_developer/
├── ai_dev/
│   ├── core/                    # 核心组件
│   │   ├── assistant.py         # AI助手主类
│   │   ├── re_act_agent.py      # ReAct架构代理
│   │   ├── config_manager.py    # 配置管理
│   │   ├── global_state.py      # 全局状态管理
│   │   └── interruption_manager.py  # 中断管理
│   ├── tools/                   # 工具系统
│   │   ├── base.py              # 工具基类
│   │   ├── file_read.py         # 文件读取
│   │   ├── file_write.py        # 文件写入
│   │   ├── file_edit.py         # 文件编辑
│   │   ├── file_list.py         # 文件列表
│   │   ├── grep.py              # 内容搜索
│   │   ├── glob.py              # 文件匹配
│   │   ├── bash_exec.py         # 命令执行
│   │   ├── todo_write.py        # 任务管理
│   │   └── task_tool.py         # 任务工具
│   ├── cli/                     # 命令行界面
│   │   ├── advanced_cli.py      # 高级CLI实现
│   │   └── cli.py               # 基础CLI
│   ├── commands/                # 内置命令
│   │   ├── help.py              # 帮助命令
│   │   ├── clear.py             # 清除命令
│   │   └── agents.py            # 代理命令
│   ├── models/                  # 数据模型
│   │   ├── state.py             # 状态模型
│   │   └── model_manager.py     # 模型管理
│   ├── permission/              # 权限系统
│   │   ├── permission_manager.py
│   │   └── permission_ui.py
│   ├── utils/                   # 工具类
│   │   ├── logger.py            # 日志系统
│   │   ├── stream_processor.py  # 流式处理
│   │   └── render.py            # 输出渲染
│   └── components/              # UI组件
│       ├── output_capture.py    # 输出捕获
│       └── scrollable_formatted_text_control.py  # 滚动控件
├── pyproject.toml               # 项目配置
└── README.md
```

## 技术架构

### 核心架构
- **ReAct模式** - 推理-行动循环，基于LangGraph实现
- **流式处理** - 实时显示AI响应和工具执行进度
- **权限系统** - 三级权限控制（自动/询问/拒绝）
- **中断恢复** - 支持权限中断和用户交互恢复
- **并行执行** - 智能工具并行调度

### 工具系统
- `FileReadTool` - 文件读取
- `FileWriteTool` - 文件写入
- `FileEditTool` - 文件编辑
- `FileListTool` - 文件列表
- `GrepTool` - 内容搜索
- `GlobTool` - 文件匹配
- `BashExecTool` - 命令执行
- `TodoWriteTool` - 任务管理
- `TaskTool` - 任务工具

## 开发计划

### 已实现功能
- ✅ **高级CLI界面** - 基于prompt_toolkit的交互式体验
- ✅ **ReAct架构** - 基于LangGraph的推理-行动循环
- ✅ **权限系统** - 三级权限控制和中断恢复
- ✅ **工具系统** - 可扩展的工具注册和管理
- ✅ **流式输出** - 实时显示AI响应和工具进度
- ✅ **任务管理** - TodoWrite工具跟踪任务进度
- ✅ **实时输入** - 允许用户实时输入，可自动排队用户输入，适时自动处理
- ✅ **模块化输出** - 按块输出内容，支持按块更新信息
- ✅ **上下文自动压缩** - 自动检测上下文长度，当达到阈值时自动压缩上下文
- ✅ **文件新鲜度** - 自动检测agent需要修改的文件是不是已经读取过以及在最后读取/修改之后有没有被外部修改过
- ✅ **支持MCP工具调用** - 自动注册使用项目.ai_dev/mcp及~/.ai_dev/mcp下配置的MCP Server

### 后续版本功能
- [ ] 增加切换显示多行文本
- [ ] 扩展工具列表，增加网络搜索、访问指定URL、调用其他模型等

## 贡献

欢迎提交Issue和Pull Request来改进这个项目！

## 许可证

Apache 2.0 许可证 - 详见 [LICENSE](LICENSE)。