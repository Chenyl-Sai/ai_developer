import asyncio

from .exec_file import exec_file_no_throw

async def get_is_git():
    """判断执行当前项目是否是git项目

    Return:
        bool: Ture/False
    """
    result = exec_file_no_throw('git', [
        'rev-parse',
        '--is-inside-work-tree',
    ])
    return result.get("code") == 0
