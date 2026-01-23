"""配置变更回调管理器"""

import threading
from typing import Any, Callable, Dict, List, Optional


class ConfigCallbackManager:
    """
    配置变更回调管理器

    支持两种回调类型：
    1. 单键回调：监听特定配置项的变更
    2. 全局回调：监听所有配置项的变更

    线程安全，支持并发注册/注销/通知
    """

    def __init__(self):
        """初始化回调管理器"""
        # 单键回调: key -> [callback1, callback2, ...]
        self._callbacks: Dict[str, List[Callable[[Any], None]]] = {}

        # 全局回调: 监听所有变更
        self._global_callbacks: List[Callable[[str, Any, Any], None]] = []

        # 线程锁
        self._lock = threading.Lock()

    def register(self, key: str, callback: Callable[[Any], None]) -> None:
        """
        注册单个配置项的变更回调

        Args:
            key: 配置项键名
            callback: 回调函数，签名为 callback(new_value)
        """
        with self._lock:
            if key not in self._callbacks:
                self._callbacks[key] = []
            if callback not in self._callbacks[key]:
                self._callbacks[key].append(callback)

    def register_global(self, callback: Callable[[str, Any, Any], None]) -> None:
        """
        注册全局变更回调（监听所有配置变化）

        Args:
            callback: 回调函数，签名为 callback(key, new_value, old_value)
        """
        with self._lock:
            if callback not in self._global_callbacks:
                self._global_callbacks.append(callback)

    def unregister(self, key: str, callback: Callable[[Any], None]) -> bool:
        """
        取消注册单键回调

        Args:
            key: 配置项键名
            callback: 要取消的回调函数

        Returns:
            是否成功取消
        """
        with self._lock:
            if key in self._callbacks and callback in self._callbacks[key]:
                self._callbacks[key].remove(callback)
                # 清理空列表
                if not self._callbacks[key]:
                    del self._callbacks[key]
                return True
            return False

    def unregister_global(self, callback: Callable[[str, Any, Any], None]) -> bool:
        """
        取消注册全局回调

        Args:
            callback: 要取消的回调函数

        Returns:
            是否成功取消
        """
        with self._lock:
            if callback in self._global_callbacks:
                self._global_callbacks.remove(callback)
                return True
            return False

    def unregister_all(self, key: Optional[str] = None) -> int:
        """
        取消注册所有回调

        Args:
            key: 如果指定，只清除该键的回调；否则清除所有回调

        Returns:
            清除的回调数量
        """
        with self._lock:
            if key is not None:
                if key in self._callbacks:
                    count = len(self._callbacks[key])
                    del self._callbacks[key]
                    return count
                return 0
            else:
                count = sum(len(cbs) for cbs in self._callbacks.values())
                count += len(self._global_callbacks)
                self._callbacks.clear()
                self._global_callbacks.clear()
                return count

    def notify(self, key: str, new_value: Any, old_value: Any = None) -> int:
        """
        通知配置变更

        Args:
            key: 变更的配置项键名
            new_value: 新值
            old_value: 旧值（可选）

        Returns:
            成功执行的回调数量
        """
        # 在锁内复制回调列表，避免迭代时修改
        with self._lock:
            key_callbacks = self._callbacks.get(key, []).copy()
            global_callbacks = self._global_callbacks.copy()

        success_count = 0

        # 调用特定 key 的回调
        for cb in key_callbacks:
            try:
                cb(new_value)
                success_count += 1
            except Exception as e:
                print(f"[ConfigCallback] 回调执行失败 ({key}): {e}")

        # 调用全局回调
        for cb in global_callbacks:
            try:
                cb(key, new_value, old_value)
                success_count += 1
            except Exception as e:
                print(f"[ConfigCallback] 全局回调执行失败: {e}")

        return success_count

    def notify_batch(self, changes: Dict[str, tuple]) -> int:
        """
        批量通知变更

        Args:
            changes: 变更字典，格式为 {key: (old_value, new_value)}

        Returns:
            成功执行的回调总数
        """
        total_count = 0
        for key, (old_val, new_val) in changes.items():
            total_count += self.notify(key, new_val, old_val)
        return total_count

    def get_registered_keys(self) -> List[str]:
        """
        获取所有已注册回调的键名

        Returns:
            键名列表
        """
        with self._lock:
            return list(self._callbacks.keys())

    def get_callback_count(self, key: Optional[str] = None) -> int:
        """
        获取回调数量

        Args:
            key: 如果指定，返回该键的回调数量；否则返回总数

        Returns:
            回调数量
        """
        with self._lock:
            if key is not None:
                return len(self._callbacks.get(key, []))
            else:
                return sum(len(cbs) for cbs in self._callbacks.values()) + len(self._global_callbacks)

    def has_callbacks(self, key: str) -> bool:
        """
        检查指定键是否有注册的回调

        Args:
            key: 配置项键名

        Returns:
            是否有回调
        """
        with self._lock:
            return key in self._callbacks and len(self._callbacks[key]) > 0


# ========== 全局单例 ==========

_callback_manager: Optional[ConfigCallbackManager] = None
_manager_lock = threading.Lock()


def get_callback_manager() -> ConfigCallbackManager:
    """
    获取回调管理器全局单例

    Returns:
        ConfigCallbackManager 实例
    """
    global _callback_manager
    if _callback_manager is None:
        with _manager_lock:
            if _callback_manager is None:
                _callback_manager = ConfigCallbackManager()
    return _callback_manager


# ========== 便捷函数 ==========

def on_config_change(key: str, callback: Callable[[Any], None]) -> None:
    """
    注册配置变更回调（便捷函数）

    Args:
        key: 配置项键名
        callback: 回调函数，签名为 callback(new_value)
    """
    get_callback_manager().register(key, callback)


def off_config_change(key: str, callback: Callable[[Any], None]) -> bool:
    """
    取消配置变更回调（便捷函数）

    Args:
        key: 配置项键名
        callback: 要取消的回调函数

    Returns:
        是否成功取消
    """
    return get_callback_manager().unregister(key, callback)


def on_any_config_change(callback: Callable[[str, Any, Any], None]) -> None:
    """
    注册全局配置变更回调（便捷函数）

    Args:
        callback: 回调函数，签名为 callback(key, new_value, old_value)
    """
    get_callback_manager().register_global(callback)


def off_any_config_change(callback: Callable[[str, Any, Any], None]) -> bool:
    """
    取消全局配置变更回调（便捷函数）

    Args:
        callback: 要取消的回调函数

    Returns:
        是否成功取消
    """
    return get_callback_manager().unregister_global(callback)


def notify_config_change(key: str, new_value: Any, old_value: Any = None) -> int:
    """
    通知配置变更（便捷函数）

    Args:
        key: 变更的配置项键名
        new_value: 新值
        old_value: 旧值（可选）

    Returns:
        成功执行的回调数量
    """
    return get_callback_manager().notify(key, new_value, old_value)
