"""
Unit tests for freshness.py
"""

import os
import time
import tempfile
import pytest
from pathlib import Path

from ai_dev.utils.freshness import (
    FileFreshnessRecord,
    update_read_time,
    update_agent_edit_time,
    check_freshness,
    get_record,
    clear_record,
    clear_all,
    get_stats
)


class TestFileFreshnessRecord:
    """Test FileFreshnessRecord dataclass"""
    
    def test_record_creation(self):
        """Test creating a FileFreshnessRecord"""
        record = FileFreshnessRecord(
            file_path="/test/file.txt",
            last_read_time=1234567890.0,
            last_agent_edit_time=1234567891.0,
            last_external_edit_time=1234567892.0,
            read_count=5
        )
        
        assert record.file_path == "/test/file.txt"
        assert record.last_read_time == 1234567890.0
        assert record.last_agent_edit_time == 1234567891.0
        assert record.last_external_edit_time == 1234567892.0
        assert record.read_count == 5
    
    def test_record_default_values(self):
        """Test FileFreshnessRecord with default values"""
        record = FileFreshnessRecord(file_path="/test/file.txt")
        
        assert record.file_path == "/test/file.txt"
        assert record.last_read_time is None
        assert record.last_agent_edit_time is None
        assert record.last_external_edit_time is None
        assert record.read_count == 0


class TestFreshnessFunctions:
    """Test freshness utility functions"""
    
    def setup_method(self):
        """Clear all records before each test"""
        clear_all()
    
    def test_update_read_time_new_file(self):
        """Test updating read time for a new file"""
        file_path = "/test/file.txt"
        
        update_read_time(file_path)
        record = get_record(file_path)
        
        assert record is not None
        assert record.file_path == file_path
        assert record.last_read_time is not None
        assert record.last_agent_edit_time is None
        assert record.read_count == 1
    
    def test_update_read_time_existing_file(self):
        """Test updating read time for an existing file"""
        file_path = "/test/file.txt"
        
        # First read
        update_read_time(file_path)
        first_read_time = get_record(file_path).last_read_time
        
        # Small delay to ensure different timestamps
        time.sleep(0.01)
        
        # Second read
        update_read_time(file_path)
        second_read_time = get_record(file_path).last_read_time
        
        assert second_read_time > first_read_time
        assert get_record(file_path).read_count == 2
        assert get_record(file_path).last_agent_edit_time is None
    
    def test_update_agent_edit_time(self):
        """Test updating agent edit time"""
        file_path = "/test/file.txt"
        
        update_agent_edit_time(file_path)
        record = get_record(file_path)
        
        assert record is not None
        assert record.last_agent_edit_time is not None
        assert record.last_read_time is None
        assert record.read_count == 0
    
    def test_update_agent_edit_time_after_read(self):
        """Test updating agent edit time after reading"""
        file_path = "/test/file.txt"
        
        update_read_time(file_path)
        update_agent_edit_time(file_path)
        record = get_record(file_path)
        
        assert record.last_agent_edit_time is not None
        assert record.last_read_time is not None
        assert record.read_count == 1


class TestCheckFreshness:
    """Test check_freshness function"""
    
    def setup_method(self):
        """Clear all records before each test"""
        clear_all()
    
    def test_check_freshness_no_record(self):
        """Test checking freshness for file with no record"""
        file_path = "/test/file.txt"
        
        needs_read, reason = check_freshness(file_path)
        
        assert needs_read is True
        assert "修改之前必须先使用FileReadTool读取文件" in reason
    
    def test_check_freshness_with_real_file(self):
        """Test checking freshness with a real temporary file"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_file = f.name
        
        try:
            # Record initial read
            update_read_time(temp_file)
            
            # Check freshness immediately - should be fresh
            needs_read, reason = check_freshness(temp_file)
            assert needs_read is False
            assert "文件内容未变更" in reason
            
            # Modify the file
            time.sleep(0.01)  # Ensure different timestamp
            with open(temp_file, 'w') as f:
                f.write("modified content")
            
            # Check freshness after modification - should need read
            needs_read, reason = check_freshness(temp_file)
            assert needs_read is True
            assert "文件已被用户修改，请重新读取后再修改" in reason
            
        finally:
            os.unlink(temp_file)
    
    def test_check_freshness_after_agent_edit(self):
        """Test freshness check after agent edit"""
        # 创建临时文件
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            file_path = os.path.abspath(f.name)

            # Simulate agent edit
            update_agent_edit_time(file_path)

            # Check freshness - should be fresh
            needs_read, reason = check_freshness(file_path)
            assert needs_read is False
            assert "agent有最新鲜的数据" in reason
    
    def test_check_freshness_nonexistent_file(self):
        """Test checking freshness for non-existent file"""
        file_path = "/nonexistent/file.txt"
        
        # Create record first
        update_read_time(file_path)
        
        # Check freshness - should need read due to file not existing
        needs_read, reason = check_freshness(file_path)
        assert needs_read is True
        assert "文件不存在或无法访问" in reason


class TestUtilityFunctions:
    """Test utility functions"""
    
    def setup_method(self):
        """Clear all records before each test"""
        clear_all()
    
    def test_get_record(self):
        """Test getting record"""
        file_path = "/test/file.txt"
        
        # No record initially
        assert get_record(file_path) is None
        
        # Create record
        update_read_time(file_path)
        record = get_record(file_path)
        
        assert record is not None
        assert record.file_path == file_path
    
    def test_clear_record(self):
        """Test clearing individual record"""
        file_path = "/test/file.txt"
        
        update_read_time(file_path)
        assert get_record(file_path) is not None
        
        clear_record(file_path)
        assert get_record(file_path) is None
    
    def test_clear_all(self):
        """Test clearing all records"""
        file1 = "/test/file1.txt"
        file2 = "/test/file2.txt"
        
        update_read_time(file1)
        update_read_time(file2)
        
        assert get_record(file1) is not None
        assert get_record(file2) is not None
        
        clear_all()
        
        assert get_record(file1) is None
        assert get_record(file2) is None
    
    def test_get_stats(self):
        """Test getting statistics"""
        # Initially empty
        stats = get_stats()
        assert stats["total_files"] == 0
        assert stats["total_reads"] == 0
        assert stats["files_with_reads"] == 0
        assert stats["files_edited"] == 0
        
        # Add some records
        update_read_time("/test/file1.txt")
        update_read_time("/test/file1.txt")  # Second read
        update_read_time("/test/file2.txt")
        update_agent_edit_time("/test/file3.txt")
        
        stats = get_stats()
        assert stats["total_files"] == 3
        assert stats["total_reads"] == 3  # file1 read twice, file2 read once
        assert stats["files_with_reads"] == 2  # file1 and file2
        assert stats["files_edited"] == 1  # file3


class TestIntegrationScenarios:
    """Test integration scenarios"""
    
    def setup_method(self):
        """Clear all records before each test"""
        clear_all()
    
    def test_complete_workflow(self):
        """Test complete freshness workflow"""
        import tempfile
        import os
        
        # Create a temporary file for testing
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("initial content")
            file_path = f.name
        
        try:
            # Step 1: Read file
            update_read_time(file_path)
            record = get_record(file_path)
            assert record.read_count == 1
            assert record.last_read_time is not None
            assert record.last_agent_edit_time is None
            
            # Step 2: Check freshness (should be fresh)
            needs_read, reason = check_freshness(file_path)
            assert needs_read is False
            
            # Step 3: Agent edits file
            update_agent_edit_time(file_path)
            record = get_record(file_path)
            assert record.last_agent_edit_time is not None
            
            # Step 4: Check freshness after agent edit (should be fresh)
            needs_read, reason = check_freshness(file_path)
            assert needs_read is False
            assert "agent有最新鲜的数据" in reason
            
            # Step 5: Clear record
            clear_record(file_path)
            assert get_record(file_path) is None
            
            # Step 6: Check freshness after clear (should need read)
            needs_read, reason = check_freshness(file_path)
            assert needs_read is True
            assert "修改之前必须先使用FileReadTool读取文件" in reason
        finally:
            os.unlink(file_path)