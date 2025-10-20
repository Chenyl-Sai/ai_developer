"""
文件新鲜度工具函数
"""

import os
import time
from typing import Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class FileFreshnessRecord:
    """文件新鲜度记录"""
    file_path: str
    last_read_time: Optional[float] = None      # 最后一次被agent读取的时间
    last_agent_edit_time: Optional[float] = None # 从上次读取之后，最近一次被agent修改的时间
    last_external_edit_time: Optional[float] = None # 最后一次外部修改时间
    read_count: int = 0                         # 读取次数统计


# 全局记录存储
_freshness_records: Dict[str, FileFreshnessRecord] = {}


def update_read_time(file_path: str):
    """更新文件读取时间"""
    record = _get_or_create_record(file_path)
    record.last_read_time = time.time()
    record.read_count += 1
    
    # 清空agent修改时间
    record.last_agent_edit_time = None
    
    # 更新外部修改时间为当前文件修改时间
    try:
        record.last_external_edit_time = _get_file_mtime(file_path)
    except (OSError, FileNotFoundError):
        pass
        

def update_agent_edit_time(file_path: str):
    """更新agent修改时间"""
    record = _get_or_create_record(file_path)
    record.last_agent_edit_time = time.time()

    # 更新外部修改时间为当前文件修改时间
    try:
        record.last_external_edit_time = _get_file_mtime(file_path)
    except (OSError, FileNotFoundError):
        pass
        

def check_freshness(file_path: str) -> Tuple[bool, str]:
    """
    检查文件新鲜度
    返回: (是否需要重新读取, 原因)
    """
    if file_path not in _freshness_records:
        return True, "修改之前必须先使用FileReadTool读取文件"
        
    record = _freshness_records[file_path]
    
    # 优先检查agent修改时间
    if record.last_agent_edit_time is not None:
        # 如果agent修改过文件，检查文件是否在agent修改后被外部修改
        try:
            current_mtime = _get_file_mtime(file_path)
            record.last_external_edit_time = current_mtime
            if current_mtime > record.last_agent_edit_time:
                return True, "文件已被用户修改，请重新读取后再修改"
        except (OSError, FileNotFoundError):
            # 文件不存在，但之前读取过，说明文件被删除了或从未存在
            return True, "文件不存在或无法访问"
        return False, "agent有最新鲜的数据"
    
    # 如果没有agent修改时间，检查读取时间
    elif record.last_read_time is not None:
        try:
            current_mtime = _get_file_mtime(file_path)
            record.last_external_edit_time = current_mtime
            if current_mtime > record.last_read_time:
                return True, "文件已被用户修改，请重新读取后再修改"
            return False, "文件内容未变更"
        except (OSError, FileNotFoundError):
            # 文件不存在，但之前读取过，说明文件被删除了或从未存在
            return True, "文件不存在或无法访问"
    
    # 既没有读取时间也没有agent修改时间
    return True, "修改之前必须先使用FileReadTool读取文件"

def get_record(file_path: str) -> Optional[FileFreshnessRecord]:
    """获取文件记录"""
    return _freshness_records.get(file_path)

def clear_record(file_path: str):
    """清除文件记录"""
    if file_path in _freshness_records:
        del _freshness_records[file_path]

def clear_all():
    """清除所有记录"""
    _freshness_records.clear()

def get_stats() -> Dict:
    """获取统计信息"""
    return {
        "total_files": len(_freshness_records),
        "total_reads": sum(record.read_count for record in _freshness_records.values()),
        "files_with_reads": sum(1 for record in _freshness_records.values() if record.read_count > 0),
        "files_edited": sum(1 for record in _freshness_records.values() if record.last_agent_edit_time),
    }
    
def _get_or_create_record(file_path: str) -> FileFreshnessRecord:
    """获取或创建记录"""
    if file_path not in _freshness_records:
        _freshness_records[file_path] = FileFreshnessRecord(file_path)
    return _freshness_records[file_path]
    
def _get_file_mtime(file_path: str) -> float:
    """获取文件修改时间"""
    return os.path.getmtime(file_path)