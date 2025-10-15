import logging
import subprocess
from typing import Optional, Dict, Any
from ai_dev.core.global_state import GlobalState

logger = logging.getLogger(__name__)

MS_IN_SECOND = 1000
SECONDS_IN_MINUTE = 60

def exec_file_no_throw(
    file: str,
    args: list[str],
    timeout: int = 10 * SECONDS_IN_MINUTE * MS_IN_SECOND,
    preserve_output_on_error: bool = True,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run subprocess command but never raise.
    Always return dict {stdout, stderr, code}.
    timeout 单位：毫秒
    """
    try:
        result = subprocess.run(
            [file] + args,
            capture_output=True,
            text=True,
            cwd=cwd or GlobalState.get_working_directory(),
            timeout=timeout / 1000.0,  # Python timeout 是秒
        )
        return {
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "code": result.returncode,
        }
    except subprocess.TimeoutExpired as e:
        # 超时情况
        if preserve_output_on_error:
            return {
                "stdout": e.stdout or "",
                "stderr": e.stderr or "",
                "code": 1,
            }
        return {"stdout": "", "stderr": "", "code": 1}
    except Exception as e:
        logger.error("Exec file Failed:", exc_info=e)
        if preserve_output_on_error:
            return {"stdout": "", "stderr": str(e), "code": 1}
        return {"stdout": "", "stderr": "", "code": 1}
