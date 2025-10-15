#!/usr/bin/env python3
"""
测试 GlobTool 逻辑的测试代码
"""

import unittest
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# 添加项目路径到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_dev.tools.glob import GlobTool


class TestGlobTool(unittest.TestCase):
    """测试 GlobTool 类"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.glob_tool = GlobTool(working_directory=str(self.test_dir))

        # 创建测试文件
        self.create_test_files()

    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.test_dir)

    def create_test_files(self):
        """创建测试文件"""
        # 创建不同扩展名的测试文件
        files_content = {
            "test_python.py": """
def hello_world():
    print("Hello, World!")
    return True
""",
            "test_javascript.js": """
function helloWorld() {
    console.log("Hello, World!");
    return true;
}
""",
            "test_text.txt": """
This is a test file.
It contains some test content.
""",
            "config.json": """
{
    "name": "test",
    "version": "1.0.0"
}
""",
            "README.md": """
# Test Project
This is a test project.
""",
            "subdir/test_nested.py": """
def nested_function():
    print("This is in a subdirectory")
    return "nested"
""",
            "subdir/another_file.js": """
function anotherFunction() {
    return "another";
}
""",
            "subdir/deeply/nested/file.py": """
def deeply_nested():
    return "deeply nested"
"""
        }

        # 写入文件
        for filename, content in files_content.items():
            file_path = self.test_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

    def test_glob_tool_initialization(self):
        """测试 GlobTool 初始化"""
        self.assertEqual(self.glob_tool.name, "GlobTool")
        self.assertEqual(self.glob_tool.show_name, "Search")
        self.assertTrue(self.glob_tool.is_readonly)
        self.assertTrue(self.glob_tool.is_parallelizable)
        self.assertIsNotNone(self.glob_tool.description)
        self.assertIsNotNone(self.glob_tool.input_schema)
        self.assertIsNotNone(self.glob_tool.model_prompt)

    def test_glob_tool_input_schema(self):
        """测试输入参数 schema"""
        schema = self.glob_tool.input_schema
        self.assertEqual(schema["type"], "object")
        self.assertIn("directory", schema["required"])
        self.assertIn("pattern", schema["required"])
        self.assertIn("directory", schema["properties"])
        self.assertIn("pattern", schema["properties"])

    def test_glob_basic_pattern(self):
        """测试基本模式匹配"""
        # 测试匹配所有 Python 文件
        results = self.glob_tool.execute(directory=str(self.test_dir), pattern="*.py")

        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

        # 验证只返回 Python 文件
        for result in results:
            self.assertTrue(result["name"].endswith(".py"))
            self.assertIn("name", result)
            self.assertIn("path", result)
            self.assertIn("size", result)
            self.assertIn("modified", result)

    def test_glob_recursive_pattern(self):
        """测试递归模式匹配"""
        # 测试递归匹配所有 Python 文件
        results = self.glob_tool.execute(directory=str(self.test_dir), pattern="**/*.py")

        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

        # 验证包含嵌套目录中的文件
        nested_found = any("subdir" in result["path"] for result in results)
        self.assertTrue(nested_found)

    def test_glob_multiple_extensions(self):
        """测试多扩展名匹配"""
        # 测试匹配 Python 和 JavaScript 文件
        # 使用多个 glob 模式
        results_py = self.glob_tool.execute(directory=str(self.test_dir), pattern="*.py")
        results_js = self.glob_tool.execute(directory=str(self.test_dir), pattern="*.js")

        # 验证两种扩展名都有匹配结果
        self.assertGreater(len(results_py), 0)
        self.assertGreater(len(results_js), 0)

        # 验证 Python 文件
        for result in results_py:
            self.assertTrue(result["name"].endswith(".py"))

        # 验证 JavaScript 文件
        for result in results_js:
            self.assertTrue(result["name"].endswith(".js"))

    def test_glob_specific_directory(self):
        """测试指定子目录搜索"""
        subdir_path = self.test_dir / "subdir"

        # 在子目录中搜索
        results = self.glob_tool.execute(directory=str(subdir_path), pattern="*.py")

        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

        # 验证只返回子目录中的 Python 文件
        for result in results:
            self.assertTrue(result["name"].endswith(".py"))
            self.assertIn("subdir", result["path"])

    def test_glob_no_matches(self):
        """测试无匹配结果的情况"""
        # 测试不存在的模式
        results = self.glob_tool.execute(directory=str(self.test_dir), pattern="*.nonexistent")

        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 0)

    def test_glob_nonexistent_directory(self):
        """测试不存在的目录"""
        nonexistent_dir = self.test_dir / "nonexistent_subdir"

        with self.assertRaises(FileNotFoundError):
            self.glob_tool.execute(directory=str(nonexistent_dir), pattern="*.py")

    def test_glob_file_as_directory(self):
        """测试文件作为目录的情况"""
        file_path = self.test_dir / "test_python.py"

        with self.assertRaises(ValueError):
            self.glob_tool.execute(directory=str(file_path), pattern="*.py")

    def test_glob_result_format(self):
        """测试结果格式"""
        results = self.glob_tool.execute(directory=str(self.test_dir), pattern="*.py")

        self.assertIsInstance(results, list)

        for result in results:
            self.assertIn("name", result)
            self.assertIn("path", result)
            self.assertIn("size", result)
            self.assertIn("modified", result)

            # 验证数据类型
            self.assertIsInstance(result["name"], str)
            self.assertIsInstance(result["path"], str)
            self.assertIsInstance(result["size"], int)
            self.assertIsInstance(result["modified"], float)

            # 验证路径是相对路径
            self.assertFalse(result["path"].startswith("/"))

    def test_glob_sorted_by_modification_time(self):
        """测试结果按修改时间排序"""
        results = self.glob_tool.execute(directory=str(self.test_dir), pattern="*.py")

        if len(results) > 1:
            # 验证结果按修改时间排序（最新的在前）
            modifications = [result["modified"] for result in results]
            self.assertEqual(modifications, sorted(modifications, reverse=True))

    def test_glob_safe_path_validation(self):
        """测试路径安全验证"""
        # 测试相对路径
        safe_path = self.glob_tool._safe_join_path("subdir")
        self.assertTrue(str(safe_path).startswith(str(self.test_dir.resolve())))

        # 测试超出工作目录的路径
        with self.assertRaises(PermissionError):
            self.glob_tool._safe_join_path("../../../etc/passwd")

    def test_glob_with_dot_directory(self):
        """测试使用当前目录"""
        # 使用当前目录
        results = self.glob_tool.execute(directory=".", pattern="*.py")

        self.assertIsInstance(results, list)
        # 应该至少包含根目录下的 Python 文件
        root_py_found = any("/" not in result["path"] and result["name"].endswith(".py")
                          for result in results)
        self.assertTrue(root_py_found)

    def test_glob_with_empty_pattern(self):
        """测试空模式"""
        # 空模式不被允许，应该抛出异常
        with self.assertRaises(ValueError):
            self.glob_tool.execute(directory=str(self.test_dir), pattern="")

    def test_glob_with_single_character_pattern(self):
        """测试单字符模式"""
        # 测试单字符通配符
        results = self.glob_tool.execute(directory=str(self.test_dir), pattern="test_*.py")

        self.assertIsInstance(results, list)
        for result in results:
            self.assertTrue(result["name"].startswith("test_"))
            self.assertTrue(result["name"].endswith(".py"))

    def test_glob_exclude_directories(self):
        """测试不包含目录"""
        # 验证只返回文件，不包含目录
        results = self.glob_tool.execute(directory=str(self.test_dir), pattern="*")

        for result in results:
            # 确保路径指向文件（不是目录）
            file_path = self.test_dir / result["path"]
            self.assertTrue(file_path.is_file())


class TestGlobToolIntegration(unittest.TestCase):
    """集成测试 - 实际执行 glob 操作"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.glob_tool = GlobTool(working_directory=str(self.test_dir))

        # 创建简单的测试文件
        test_files = [
            "integration_test.py",
            "integration_test.js",
            "integration_test.txt",
            "subdir/nested_test.py"
        ]

        for filename in test_files:
            file_path = self.test_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"# {filename}")

    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.test_dir)

    def test_glob_integration_basic(self):
        """集成测试 - 基本模式匹配"""
        results = self.glob_tool.execute(directory=str(self.test_dir), pattern="*.py")

        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

        # 验证结果格式
        for result in results:
            self.assertIn("name", result)
            self.assertIn("path", result)
            self.assertIn("size", result)
            self.assertIn("modified", result)
            self.assertTrue(result["name"].endswith(".py"))

    def test_glob_integration_recursive(self):
        """集成测试 - 递归模式匹配"""
        results = self.glob_tool.execute(directory=str(self.test_dir), pattern="**/*.py")
        print(results)

        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

        # 验证包含嵌套文件
        nested_found = any("subdir" in result["path"] for result in results)
        self.assertTrue(nested_found)

    def test_glob_integration_multiple_extensions(self):
        """集成测试 - 多扩展名匹配"""
        # 分别测试两种扩展名
        results_py = self.glob_tool.execute(directory=str(self.test_dir), pattern="*.py")
        results_js = self.glob_tool.execute(directory=str(self.test_dir), pattern="*.js")

        # 验证两种扩展名都有匹配结果
        self.assertGreater(len(results_py), 0)
        self.assertGreater(len(results_js), 0)

        # 验证 Python 文件
        for result in results_py:
            self.assertTrue(result["name"].endswith(".py"))

        # 验证 JavaScript 文件
        for result in results_js:
            self.assertTrue(result["name"].endswith(".js"))

    def test123(self):
        test_dir = Path("/Users/sai/Documents/work/pythonWorkspace/ai_developer_deepseek/ai_dev")
        glob_tool = GlobTool(working_directory=str(test_dir))
        results_py = glob_tool.execute(directory=str(test_dir) + "/tools", pattern="*.py")
        print(results_py)


if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)