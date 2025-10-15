"""
错误监控和报告 - 监控异常频率和模式
"""

import time
from collections import defaultdict, deque
from typing import Dict, List, Optional
from datetime import datetime, timedelta
# 延迟导入以避免循环导入
# from .logger import agent_logger


class ErrorMonitor:
    """错误监控器"""

    def __init__(self, window_size: int = 100, time_window: int = 3600):
        """
        初始化错误监控器

        Args:
            window_size: 滑动窗口大小
            time_window: 时间窗口大小（秒）
        """
        self.window_size = window_size
        self.time_window = time_window

        # 错误统计
        self.error_counts = defaultdict(int)
        self.error_timestamps = deque()
        self.error_types = defaultdict(int)

        # 错误模式检测
        self.recent_errors = deque(maxlen=window_size)

    def record_error(self, error_type: str, context: str = ""):
        """
        记录错误

        Args:
            error_type: 错误类型
            context: 错误上下文
        """
        current_time = time.time()

        # 记录错误
        self.error_counts[error_type] += 1
        self.error_types[error_type] += 1
        self.error_timestamps.append(current_time)

        # 记录错误模式
        self.recent_errors.append({
            "timestamp": current_time,
            "type": error_type,
            "context": context
        })

        # 清理过期的错误记录
        self._cleanup_old_errors()

    def _cleanup_old_errors(self):
        """清理过期的错误记录"""
        current_time = time.time()
        cutoff_time = current_time - self.time_window

        # 清理时间戳
        while self.error_timestamps and self.error_timestamps[0] < cutoff_time:
            self.error_timestamps.popleft()

        # 清理错误模式记录
        while self.recent_errors and self.recent_errors[0]["timestamp"] < cutoff_time:
            self.recent_errors.popleft()

    def get_error_rate(self) -> float:
        """
        获取当前错误率

        Returns:
            每分钟的错误率
        """
        if not self.error_timestamps:
            return 0.0

        current_time = time.time()
        cutoff_time = current_time - 60  # 最近一分钟

        recent_errors = sum(1 for ts in self.error_timestamps if ts > cutoff_time)
        return recent_errors

    def get_error_summary(self) -> Dict:
        """
        获取错误摘要

        Returns:
            错误摘要信息
        """
        return {
            "total_errors": len(self.error_timestamps),
            "error_rate_per_minute": self.get_error_rate(),
            "error_types": dict(self.error_types),
            "time_window_seconds": self.time_window
        }

    def detect_error_patterns(self) -> List[Dict]:
        """
        检测错误模式

        Returns:
            检测到的错误模式列表
        """
        patterns = []

        # 检测频繁错误
        for error_type, count in self.error_types.items():
            if count >= 5:  # 同一错误类型出现5次以上
                patterns.append({
                    "type": "frequent_error",
                    "error_type": error_type,
                    "count": count,
                    "severity": "high" if count >= 10 else "medium"
                })

        # 检测错误爆发
        if self.get_error_rate() >= 10:  # 每分钟10个错误
            patterns.append({
                "type": "error_spike",
                "rate": self.get_error_rate(),
                "severity": "high"
            })

        return patterns

    def should_alert(self) -> bool:
        """
        判断是否需要发出警报

        Returns:
            是否需要警报
        """
        # 错误率过高
        if self.get_error_rate() >= 20:
            return True

        # 检测到严重错误模式
        patterns = self.detect_error_patterns()
        for pattern in patterns:
            if pattern.get("severity") == "high":
                return True

        return False

    def generate_alert(self) -> Optional[Dict]:
        """
        生成警报信息

        Returns:
            警报信息字典，如果不需要警报则返回None
        """
        if not self.should_alert():
            return None

        summary = self.get_error_summary()
        patterns = self.detect_error_patterns()

        alert = {
            "timestamp": datetime.now().isoformat(),
            "type": "error_alert",
            "summary": summary,
            "patterns": patterns,
            "recommendations": self._generate_recommendations(patterns)
        }

        # 记录警报（延迟导入以避免循环导入）
        try:
            from .logger import agent_logger
            agent_logger.warning(f"错误警报: {alert}")
        except ImportError:
            agent_logger.error(f"错误警报: {alert}")

        return alert

    def _generate_recommendations(self, patterns: List[Dict]) -> List[str]:
        """
        生成修复建议

        Args:
            patterns: 错误模式列表

        Returns:
            修复建议列表
        """
        recommendations = []

        for pattern in patterns:
            if pattern["type"] == "frequent_error":
                recommendations.append(
                    f"检查并修复频繁出现的错误: {pattern['error_type']}"
                )
            elif pattern["type"] == "error_spike":
                recommendations.append(
                    f"系统出现错误爆发，建议检查系统状态和资源使用情况"
                )

        return recommendations

    def reset(self):
        """重置监控器"""
        self.error_counts.clear()
        self.error_timestamps.clear()
        self.error_types.clear()
        self.recent_errors.clear()


# 全局错误监控实例
error_monitor = ErrorMonitor()