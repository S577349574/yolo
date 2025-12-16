"""
事件系统 - 脚本间通信与事件分发
"""

import time
from typing import Dict, List, Callable, Any, Optional
from collections import defaultdict

import utils


class EventSystem:
    """事件系统"""

    def __init__(self):
        """初始化事件系统"""
        # 事件监听器: {事件名: [(listener_id, callback), ...]}
        self._listeners: Dict[str, List[tuple]] = defaultdict(list)

        # 监听器ID计数器
        self._next_listener_id = 0

        # 事件统计
        self._event_counts: Dict[str, int] = defaultdict(int)

        # 性能监控
        self._event_times: Dict[str, List[float]] = defaultdict(list)

    def on(self, event_name: str, callback: Callable) -> int:
        """
        注册事件监听器

        Args:
            event_name: 事件名称
            callback: 回调函数

        Returns:
            int: 监听器ID
        """
        listener_id = self._next_listener_id
        self._next_listener_id += 1

        self._listeners[event_name].append((listener_id, callback))

        if utils.get_config("SCRIPT_DEBUG_MODE", False):
            utils.log(f"[EventSystem] 注册监听器: {event_name} (ID={listener_id})")

        return listener_id

    def off(self, event_name: str, listener_id: int) -> bool:
        """
        移除事件监听器

        Args:
            event_name: 事件名称
            listener_id: 监听器ID

        Returns:
            bool: 是否成功
        """
        if event_name not in self._listeners:
            return False

        original_count = len(self._listeners[event_name])

        self._listeners[event_name] = [
            (lid, cb) for lid, cb in self._listeners[event_name]
            if lid != listener_id
        ]

        success = len(self._listeners[event_name]) < original_count

        if success and utils.get_config("SCRIPT_DEBUG_MODE", False):
            utils.log(f"[EventSystem] 移除监听器: {event_name} (ID={listener_id})")

        return success

    def emit(self, event_name: str, *args, **kwargs) -> int:
        """
        触发事件

        Args:
            event_name: 事件名称
            *args, **kwargs: 传递给回调的参数

        Returns:
            int: 成功调用的监听器数量
        """
        if event_name not in self._listeners:
            return 0

        start_time = time.perf_counter()
        success_count = 0

        for listener_id, callback in self._listeners[event_name]:
            try:
                callback(*args, **kwargs)
                success_count += 1
            except Exception as e:
                utils.log(
                    f"[EventSystem] ❌ 事件 '{event_name}' 监听器 {listener_id} 错误: {e}"
                )

        # 统计
        elapsed = time.perf_counter() - start_time
        self._event_counts[event_name] += 1
        self._event_times[event_name].append(elapsed)

        # 限制历史记录长度
        if len(self._event_times[event_name]) > 100:
            self._event_times[event_name].pop(0)

        return success_count

    def clear(self, event_name: Optional[str] = None):
        """
        清空监听器

        Args:
            event_name: 事件名称，None 表示清空所有
        """
        if event_name:
            if event_name in self._listeners:
                del self._listeners[event_name]
                utils.log(f"[EventSystem] 清空事件: {event_name}")
        else:
            self._listeners.clear()
            utils.log("[EventSystem] 清空所有事件监听器")

    def get_stats(self, event_name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取事件统计

        Args:
            event_name: 事件名称，None 返回所有统计

        Returns:
            dict: 统计信息
        """
        if event_name:
            times = self._event_times.get(event_name, [])
            avg_time = sum(times) / len(times) if times else 0

            return {
                "event": event_name,
                "listener_count": len(self._listeners.get(event_name, [])),
                "emit_count": self._event_counts.get(event_name, 0),
                "avg_time_ms": avg_time * 1000
            }
        else:
            return {
                name: {
                    "listener_count": len(listeners),
                    "emit_count": self._event_counts.get(name, 0),
                    "avg_time_ms": (
                        sum(self._event_times[name]) / len(self._event_times[name]) * 1000
                        if name in self._event_times and self._event_times[name]
                        else 0
                    )
                }
                for name, listeners in self._listeners.items()
            }
