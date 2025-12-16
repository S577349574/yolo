"""
速率限制器 - 防止脚本滥用 API
"""

import time
from typing import Dict
from collections import defaultdict

import utils


class RateLimiter:
    """速率限制器"""

    def __init__(self):
        """初始化速率限制器"""
        # 记录每个操作的调用时间
        self._call_times: Dict[str, list] = defaultdict(list)

        # 限制规则: {操作名: (时间窗口秒数, 最大调用次数)}
        self._limits = {
            "config_write": (1.0, 10),  # 每秒最多10次配置写入
            "config_batch": (1.0, 5),  # 每秒最多5次批量写入
            "log_output": (1.0, 100),  # 每秒最多100条日志
            "mouse_move": (1.0, 1000),  # 每秒最多1000次移动
            "mouse_click": (1.0, 20),  # 每秒最多20次点击
            "save_data": (60.0, 10),  # 每分钟最多10次数据保存
        }

    def check(self, operation: str, key: str = "default") -> bool:
        """
        检查是否允许执行操作

        Args:
            operation: 操作名称
            key: 唯一键（如脚本名称）

        Returns:
            bool: 是否允许
        """
        if operation not in self._limits:
            return True  # 未定义限制的操作默认允许

        window_sec, max_calls = self._limits[operation]
        current_time = time.time()

        # 生成唯一键
        rate_key = f"{operation}:{key}"

        # 清理过期记录
        self._call_times[rate_key] = [
            t for t in self._call_times[rate_key]
            if current_time - t < window_sec
        ]

        # 检查是否超过限制
        if len(self._call_times[rate_key]) >= max_calls:
            if utils.get_config("SCRIPT_DEBUG_MODE", False):
                utils.log(
                    f"[RateLimiter] ⚠ 操作 '{operation}' 被限流 "
                    f"({len(self._call_times[rate_key])}/{max_calls} in {window_sec}s)"
                )
            return False

        # 记录调用时间
        self._call_times[rate_key].append(current_time)
        return True

    def set_limit(self, operation: str, window_sec: float, max_calls: int):
        """动态设置限制规则"""
        self._limits[operation] = (window_sec, max_calls)
        utils.log(f"[RateLimiter] 设置限制: {operation} = {max_calls}次/{window_sec}秒")

    def reset(self, operation: str = None):
        """重置限制记录"""
        if operation:
            # 重置特定操作
            self._call_times = {
                k: v for k, v in self._call_times.items()
                if not k.startswith(operation + ":")
            }
        else:
            # 重置全部
            self._call_times.clear()

        utils.log(f"[RateLimiter] 已重置: {operation or '全部'}")

    def get_stats(self, operation: str = None) -> Dict:
        """获取统计信息"""
        if operation:
            # 特定操作的统计
            keys = [k for k in self._call_times if k.startswith(operation + ":")]
            total_calls = sum(len(self._call_times[k]) for k in keys)

            return {
                "operation": operation,
                "total_calls": total_calls,
                "limit": self._limits.get(operation, (0, 0))
            }
        else:
            # 全部统计
            return {
                op: {
                    "total_calls": sum(
                        len(v) for k, v in self._call_times.items()
                        if k.startswith(op + ":")
                    ),
                    "limit": limit
                }
                for op, limit in self._limits.items()
            }
