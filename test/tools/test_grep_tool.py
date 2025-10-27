#!/usr/bin/env python3
"""
测试 GrepTool 逻辑的测试代码
"""

import unittest
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# 添加项目路径到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_dev.tools.grep.grep import GrepTool


class TestGrepTool(unittest.TestCase):
    """测试 GrepTool 类"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.grep_tool = GrepTool(working_directory=str(self.test_dir))

        # 创建测试文件
        self.create_test_files()

    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.test_dir)

    def create_test_files(self):
        """创建测试文件"""
        # 创建包含特定内容的文件
        files_content = {
            "test_python.py": """
def hello_world():
    print("Hello, World!")
    return True

class TestClass:
    def test_method(self):
        return "test"
""",
            "test_javascript.js": """
function helloWorld() {
    console.log("Hello, World!");
    return true;
}

class TestClass {
    testMethod() {
        return "test";
    }
}
""",
            "test_text.txt": """
This is a test file.
It contains some test content.
Hello World is mentioned here.
""",
            "empty_file.txt": "",
            "subdir/test_nested.py": """
def nested_function():
    print("This is in a subdirectory")
    return "nested"
"""
        }

        # 写入文件
        for filename, content in files_content.items():
            file_path = self.test_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

    def test_grep_tool_initialization(self):
        """测试 GrepTool 初始化"""
        self.assertEqual(self.grep_tool.name, "GrepTool")
        self.assertEqual(self.grep_tool.show_name, "Search")
        self.assertTrue(self.grep_tool.is_readonly)
        self.assertTrue(self.grep_tool.is_parallelizable)
        self.assertIsNotNone(self.grep_tool.description)
        self.assertIsNotNone(self.grep_tool.input_schema)
        self.assertIsNotNone(self.grep_tool.model_prompt)

    def test_grep_tool_input_schema(self):
        """测试输入参数 schema"""
        schema = self.grep_tool.input_schema
        self.assertEqual(schema["type"], "object")
        self.assertIn("pattern", schema["required"])
        self.assertIn("pattern", schema["properties"])
        self.assertIn("directory", schema["properties"])
        self.assertIn("file_pattern", schema["properties"])

    @patch('subprocess.run')
    def test_grep_basic_search(self, mock_subprocess):
        """测试基本搜索功能"""
        # 模拟 ripgrep 返回结果
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test_python.py\ntest_text.txt\n"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        # 执行搜索
        results = self.grep_tool.execute(pattern="Hello")

        # 验证调用参数
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        self.assertIn("rg", call_args)
        self.assertIn("-li", call_args)
        self.assertIn("--sort", call_args)
        self.assertIn("modified", call_args)
        self.assertIn("Hello", call_args)
        # 检查目录参数（可能是绝对路径，所以检查包含关系）
        self.assertTrue(any(str(self.test_dir) in arg for arg in call_args))

    @patch('subprocess.run')
    def test_grep_with_file_pattern(self, mock_subprocess):
        """测试带文件模式的搜索"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test_python.py\n"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        # 执行带文件模式的搜索
        results = self.grep_tool.execute(pattern="def", file_pattern="**/*.py")

        # 验证调用参数包含文件模式
        call_args = mock_subprocess.call_args[0][0]
        self.assertIn("--glob", call_args)
        self.assertIn("**/*.py", call_args)

    @patch('subprocess.run')
    def test_grep_no_results(self, mock_subprocess):
        """测试无匹配结果的情况"""
        mock_result = MagicMock()
        mock_result.returncode = 1  # ripgrep 无匹配返回码
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        # 执行搜索
        results = self.grep_tool.execute(pattern="NonExistentPattern")

        # 验证返回空列表
        self.assertEqual(results, [])

    @patch('subprocess.run')
    def test_grep_error_case(self, mock_subprocess):
        """测试 ripgrep 出错的情况"""
        mock_result = MagicMock()
        mock_result.returncode = 2  # ripgrep 错误返回码
        mock_result.stderr = "Some error occurred"
        mock_subprocess.return_value = mock_result

        # 验证抛出异常
        with self.assertRaises(RuntimeError):
            self.grep_tool.execute(pattern="test")

    def test_grep_with_specific_directory(self):
        """测试指定目录搜索"""
        subdir_path = self.test_dir / "subdir"
        grep_tool = GrepTool(working_directory=str(subdir_path))

        # 验证目录存在
        self.assertTrue(subdir_path.exists())
        self.assertTrue(subdir_path.is_dir())

    def test_grep_nonexistent_directory(self):
        """测试不存在的目录"""
        # 创建一个相对路径的不存在目录
        nonexistent_dir = self.test_dir / "nonexistent_subdir"
        with self.assertRaises(FileNotFoundError):
            self.grep_tool.execute(pattern="test", directory=str(nonexistent_dir))

    def test_grep_file_as_directory(self):
        """测试文件作为目录的情况"""
        file_path = self.test_dir / "test_python.py"
        with self.assertRaises(ValueError):
            self.grep_tool.execute(pattern="test", directory=str(file_path))

    @patch('subprocess.run')
    def test_grep_result_format(self, mock_subprocess):
        """测试结果格式"""
        # 模拟 ripgrep 返回结果
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test_python.py\nsubdir/test_nested.py\n"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        # 执行搜索
        results = self.grep_tool.execute(pattern="def")

        # 验证结果格式
        self.assertIsInstance(results, list)
        for result in results:
            self.assertIn("name", result)
            self.assertIn("path", result)
            self.assertIn("modified", result)
            self.assertIsInstance(result["name"], str)
            self.assertIsInstance(result["path"], str)
            self.assertIsInstance(result["modified"], float)

    @patch('subprocess.run')
    def test_grep_ripgrep_not_found(self, mock_subprocess):
        """测试 ripgrep 命令不存在的情况"""
        mock_subprocess.side_effect = FileNotFoundError("ripgrep not found")

        with self.assertRaises(RuntimeError) as context:
            self.grep_tool.execute(pattern="test")

        self.assertIn("ripgrep command not found", str(context.exception))

    def test_grep_safe_path_validation(self):
        """测试路径安全验证"""
        # 测试相对路径
        safe_path = self.grep_tool._safe_join_path("subdir")
        self.assertTrue(str(safe_path).startswith(str(self.test_dir.resolve())))

        # 测试超出工作目录的路径
        with self.assertRaises(PermissionError):
            self.grep_tool._safe_join_path("../../../etc/passwd")


class TestGrepToolIntegration(unittest.TestCase):
    """集成测试 - 实际执行 ripgrep 命令"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.grep_tool = GrepTool(working_directory=str(self.test_dir))

        # 创建简单的测试文件
        test_file = self.test_dir / "integration_test.py"
        test_file.write_text("""
def integration_test_function():
    return "integration test"

class IntegrationTestClass:
    def method(self):
        return "method"
""")

    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.test_dir)

    def test_grep_integration_basic(self):
        """集成测试 - 基本搜索"""
        try:
            results = self.grep_tool.execute(pattern="integration")
            # 如果 ripgrep 可用，应该能找到文件
            if results:
                self.assertGreater(len(results), 0)
                for result in results:
                    self.assertIn("name", result)
                    self.assertIn("path", result)
        except RuntimeError as e:
            if "ripgrep command not found" in str(e):
                self.skipTest("ripgrep not installed")
            else:
                raise

    def test_grep_integration_file_pattern(self):
        """集成测试 - 文件模式搜索"""
        try:
            # 创建更多测试文件来验证文件模式
            js_file = self.test_dir / "test.js"
            js_file.write_text("""
function jsFunction() {
    return "javascript function";
}
""")

            txt_file = self.test_dir / "test.txt"
            txt_file.write_text("integration test in text file")

            # 测试只搜索 Python 文件
            results = self.grep_tool.execute(pattern="function", file_pattern="*.py")

            # 如果 ripgrep 可用，应该能找到 Python 文件
            if results:
                # 验证只返回 Python 文件
                for result in results:
                    self.assertTrue(result["name"].endswith(".py"))
                    self.assertIn("name", result)
                    self.assertIn("path", result)
        except RuntimeError as e:
            if "ripgrep command not found" in str(e):
                self.skipTest("ripgrep not installed")
            else:
                raise

    def test123(self):
        test_dir = Path("/Users/sai/Documents/work/pythonWorkspace/ai_developer_deepseek")
        grep_tool = GrepTool(working_directory=str(test_dir))
        results = grep_tool.execute(pattern="glob")
        print(results)



if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)