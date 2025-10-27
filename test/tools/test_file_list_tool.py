#!/usr/bin/env python3
"""
测试 FileListTool 逻辑的测试代码
"""

import unittest
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch

# 添加项目路径到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_dev.tools.file_list.file_list import FileListTool


class TestFileListTool(unittest.TestCase):
    """测试 FileListTool 类"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.file_list_tool = FileListTool(working_directory=str(self.test_dir))

        # 创建测试文件和目录结构
        self.create_test_structure()

    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.test_dir)

    def create_test_structure(self):
        """创建测试文件和目录结构"""
        # 创建文件
        files = [
            "file1.txt",
            "file2.py",
            "file3.js",
            "subdir1/subfile1.txt",
            "subdir1/subfile2.py",
            "subdir2/nested/subnested.txt"
        ]

        for file_path in files:
            full_path = self.test_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(f"Content of {file_path}")

    def test_file_list_tool_initialization(self):
        """测试 FileListTool 初始化"""
        self.assertEqual(self.file_list_tool.show_name, "LS")
        self.assertTrue(self.file_list_tool.is_readonly)
        self.assertTrue(self.file_list_tool.is_parallelizable)
        self.assertIsNotNone(self.file_list_tool.description)
        self.assertIsNotNone(self.file_list_tool.input_schema)
        self.assertIsNotNone(self.file_list_tool.model_prompt)

    def test_file_list_tool_input_schema(self):
        """测试输入参数 schema"""
        schema = self.file_list_tool.input_schema
        self.assertEqual(schema["type"], "object")
        self.assertIn("path", schema["required"])
        self.assertIn("path", schema["properties"])

        path_property = schema["properties"]["path"]
        self.assertEqual(path_property["type"], "string")
        self.assertIn("absolute path", path_property["description"].lower())

    def test_file_list_basic_execution(self):
        """测试基本文件列表功能"""
        result = self.file_list_tool.execute(path=str(self.test_dir))

        # 验证返回字符串包含预期的文件和目录
        self.assertIsInstance(result, str)
        self.assertIn("file1.txt", result)
        self.assertIn("file2.py", result)
        self.assertIn("subdir1", result)
        self.assertIn("subdir2", result)

        # 验证树形结构格式
        self.assertIn("- ", result)  # 树形结构符号
        self.assertIn("  - ", result)
        self.assertIn("    - ", result)

    def test_file_list_nonexistent_directory(self):
        """测试不存在的目录"""
        nonexistent_path = self.test_dir / "nonexistent"
        with self.assertRaises(FileNotFoundError):
            self.file_list_tool.execute(path=str(nonexistent_path))

    def test_file_list_file_as_directory(self):
        """测试文件作为目录的情况"""
        file_path = self.test_dir / "file1.txt"
        with self.assertRaises(ValueError):
            self.file_list_tool.execute(path=str(file_path))

    def test_file_list_subdirectory(self):
        """测试子目录列表"""
        subdir_path = self.test_dir / "subdir1"
        result = self.file_list_tool.execute(path=str(subdir_path))

        self.assertIn("subfile1.txt", result)
        self.assertIn("subfile2.py", result)
        # 子目录列表应该只包含该目录下的内容
        # 由于树形结构显示的是从该目录开始的树，所以会包含目录名本身
        self.assertIn("subdir1", result)
        # 不应该包含父目录的其他文件 - 使用更精确的检查
        # 检查父目录的文件名是否作为独立的行出现
        lines = result.split('\n')
        parent_files_in_result = any('file1.txt' in line and 'subfile' not in line for line in lines)
        self.assertFalse(parent_files_in_result, "父目录的文件不应该出现在子目录列表中")

    def test_file_list_depth_first_traversal(self):
        """测试深度优先遍历"""
        result = self.file_list_tool.execute(path=str(self.test_dir))

        # 验证嵌套目录结构
        self.assertIn("subdir2", result)
        self.assertIn("nested", result)
        self.assertIn("subnested.txt", result)

    def test_file_list_max_files_limit(self):
        """测试文件数量限制"""
        # 创建大量文件来测试限制
        for i in range(1500):
            file_path = self.test_dir / f"test_file_{i}.txt"
            file_path.write_text(f"Test content {i}")

        result = self.file_list_tool.execute(path=str(self.test_dir))

        # 验证超过限制时的提示信息
        self.assertIn("more than 1000 files", result)
        self.assertIn("first 1000 files", result)

    def test_file_list_permission_error_handling(self):
        """测试权限错误处理"""
        # 创建一个无法访问的目录
        restricted_dir = self.test_dir / "restricted"
        restricted_dir.mkdir()

        # 模拟权限错误
        with patch.object(Path, 'iterdir') as mock_iterdir:
            mock_iterdir.side_effect = PermissionError("Permission denied")

            # 应该不会抛出异常，而是跳过该目录
            result = self.file_list_tool.execute(path=str(self.test_dir))
            self.assertIsInstance(result, str)

    def test_file_list_tree_formatting(self):
        """测试树形结构格式化"""
        # 创建一个简单的目录结构来测试格式化
        simple_dir = Path(tempfile.mkdtemp())
        try:
            (simple_dir / "file1.txt").write_text("test")
            (simple_dir / "file2.txt").write_text("test")
            subdir = simple_dir / "subdir"
            subdir.mkdir()
            (subdir / "subfile.txt").write_text("test")

            file_list_tool = FileListTool(working_directory=str(simple_dir))
            result = file_list_tool.execute(path=str(simple_dir))

            # 验证树形结构格式
            self.assertIn("    - ", result)
            self.assertIn("  - ", result)
            self.assertIn("file1.txt", result)
            self.assertIn("file2.txt", result)
            self.assertIn("subdir", result)
            self.assertIn("subfile.txt", result)
        finally:
            import shutil
            shutil.rmtree(simple_dir)

    def test_file_list_safe_path_validation(self):
        """测试路径安全验证"""
        # 测试相对路径
        safe_path = self.file_list_tool._safe_join_path("subdir1")
        self.assertTrue(str(safe_path).startswith(str(self.test_dir.resolve())))

        # 测试超出工作目录的路径
        with self.assertRaises(PermissionError):
            self.file_list_tool._safe_join_path("../../../etc/passwd")

    def test_file_list_empty_directory(self):
        """测试空目录"""
        empty_dir = Path(tempfile.mkdtemp())
        try:
            file_list_tool = FileListTool(working_directory=str(empty_dir))
            result = file_list_tool.execute(path=str(empty_dir))

            # 空目录应该只显示目录本身
            self.assertIn(empty_dir.name, result)
            self.assertNotIn("  - ", result)  # 不应该有子项
            self.assertIn("- ", result)  # 只有根目录
        finally:
            import shutil
            shutil.rmtree(empty_dir)


class TestFileListToolIntegration(unittest.TestCase):
    """集成测试 - 实际执行文件列表功能"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.file_list_tool = FileListTool(working_directory=str(self.test_dir))

        # 创建集成测试文件结构
        self.create_integration_structure()

    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.test_dir)

    def create_integration_structure(self):
        """创建集成测试文件结构"""
        # 创建多层嵌套结构
        structure = [
            "integration_file1.py",
            "integration_file2.txt",
            "docs/readme.md",
            "docs/api/reference.md",
            "src/main.py",
            "src/utils/helper.py",
            "tests/test_main.py"
        ]

        for file_path in structure:
            full_path = self.test_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(f"# {file_path}")

    def test_file_list_integration_complex_structure(self):
        """集成测试 - 复杂目录结构"""
        result = self.file_list_tool.execute(path=str(self.test_dir))

        # 验证所有文件和目录都在结果中
        self.assertIn("integration_file1.py", result)
        self.assertIn("integration_file2.txt", result)
        self.assertIn("docs", result)
        self.assertIn("readme.md", result)
        self.assertIn("api", result)
        self.assertIn("reference.md", result)
        self.assertIn("src", result)
        self.assertIn("main.py", result)
        self.assertIn("utils", result)
        self.assertIn("helper.py", result)
        self.assertIn("tests", result)
        self.assertIn("test_main.py", result)

    def test_file_list_integration_specific_subdirectory(self):
        """集成测试 - 特定子目录"""
        src_dir = self.test_dir / "src"
        result = self.file_list_tool.execute(path=str(src_dir))

        # 验证只包含 src 目录的内容
        self.assertIn("main.py", result)
        self.assertIn("utils", result)
        self.assertIn("helper.py", result)
        self.assertNotIn("integration_file1.py", result)  # 不应该包含父目录的文件
        self.assertNotIn("docs", result)  # 不应该包含兄弟目录

    def test123(self):
        test_dir = "/Users/sai/Documents/work/pythonWorkspace/ai_developer_deepseek/ai_dev"
        file_list_tool = FileListTool(working_directory=str(test_dir))
        src_dir = Path(test_dir) / ""
        result = file_list_tool.execute(path=str(src_dir))
        print(result)



if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)