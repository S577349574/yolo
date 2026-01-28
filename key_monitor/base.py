"""按键监控抽象基类（硬件层 - 无差别监听所有按键）"""

from abc import ABC, abstractmethod
from typing import Dict, Callable, List
from threading import Thread, Event
import time
import utils


class KeyMonitorBase(ABC):
    """
    按键监控抽象基类

    职责：
    - 硬件层：始终监听所有按键状态
    - 通过回调系统通知业务层
    - 不关心业务逻辑和配置
    """

    def __init__(self, app_state, poll_interval: float = 0.05):
        """
        初始化监控器

        Args:
            app_state: 应用状态对象
            poll_interval: 轮询间隔（秒）
        """
        self.app_state = app_state
        self.poll_interval = poll_interval

        # 状态变量
        self._stop_event = Event()
        self._monitor_thread: Thread = None
        self._is_running = False

        # ⭐ 按键状态缓存（监听所有按键）
        self._last_states = {
            'left': False,
            'right': False,
            'mouse4': False,
            'mouse5': False
        }

        # ⭐ 回调字典（支持多个监听者）
        self._callbacks = {
            'left_press': [],
            'left_release': [],
            'right_press': [],
            'right_release': [],
            'mouse4_press': [],
            'mouse4_release': [],
            'mouse5_press': [],
            'mouse5_release': []
        }

    # ==================== 抽象方法（子类实现）====================

    @abstractmethod
    def is_key_pressed(self, key: str) -> bool:
        """
        检查按键是否按下（子类实现）

        Args:
            key: 按键名称（'left', 'right', 'mouse4', 'mouse5', 'f12' 等）

        Returns:
            bool: 是否按下
        """
        pass

    @abstractmethod
    def get_button_states(self) -> Dict[str, bool]:
        """
        获取所有鼠标按键状态（子类实现）

        Returns:
            Dict[str, bool]: 按键状态字典
        """
        pass

    @abstractmethod
    def _initialize(self) -> bool:
        """
        初始化监控器（子类实现）

        Returns:
            bool: 初始化是否成功
        """
        pass

    @abstractmethod
    def _cleanup(self):
        """清理资源（子类实现）"""
        pass

    # ==================== 回调注册系统 ====================

    def register_callback(self, event: str, callback: Callable):
        """
        注册回调函数（业务层使用）

        Args:
            event: 事件名称
                - 'left_press': 左键按下
                - 'left_release': 左键释放
                - 'right_press': 右键按下
                - 'right_release': 右键释放
                - 'mouse4_press': 侧键4按下
                - 'mouse4_release': 侧键4释放
                - 'mouse5_press': 侧键5按下
                - 'mouse5_release': 侧键5释放
            callback: 回调函数（无参数）
        """
        if event not in self._callbacks:
            utils.log(f"[KeyMonitor] 未知事件: {event}")
            return

        if callback not in self._callbacks[event]:
            self._callbacks[event].append(callback)
            utils.log(f"[KeyMonitor] 注册回调: {event}")
        else:
            utils.log(f"[KeyMonitor] 回调已存在: {event}")

    def unregister_callback(self, event: str, callback: Callable):
        """
        取消回调函数（业务层使用）

        Args:
            event: 事件名称
            callback: 回调函数
        """
        if event in self._callbacks and callback in self._callbacks[event]:
            self._callbacks[event].remove(callback)
            utils.log(f"[KeyMonitor] 取消回调: {event}")

    def clear_callbacks(self, event: str = None):
        """
        清空回调函数

        Args:
            event: 事件名称（None 则清空所有）
        """
        if event:
            if event in self._callbacks:
                self._callbacks[event].clear()
                utils.log(f"[KeyMonitor] 清空回调: {event}")
        else:
            for key in self._callbacks:
                self._callbacks[key].clear()
            utils.log("[KeyMonitor] 清空所有回调")

    # ==================== 生命周期管理 ====================

    def start(self) -> bool:
        """启动监控"""
        if self._is_running:
            utils.log("[KeyMonitor] 监控已在运行")
            return True

        if not self._initialize():
            utils.log("[KeyMonitor] 初始化失败")
            return False

        self._stop_event.clear()
        self._monitor_thread = Thread(
            target=self._monitor_loop,
            daemon=True,
            name="KeyMonitorThread"
        )
        self._monitor_thread.start()
        self._is_running = True

        utils.log("[KeyMonitor] 监控已启动（监听所有按键）")
        utils.log("  F12: 退出程序")
        utils.log("  其他按键: 由业务层回调处理")
        return True

    def stop(self):
        """停止监控"""
        if not self._is_running:
            return

        utils.log("[KeyMonitor] 正在停止监控...")
        self._stop_event.set()

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
            if self._monitor_thread.is_alive():
                utils.log("[KeyMonitor] 监控线程未在超时内退出")

        self._cleanup()
        self._is_running = False
        utils.log("[KeyMonitor] 监控已停止")

    def is_running(self) -> bool:
        """检查监控是否运行中"""
        return self._is_running

    # ==================== 核心监控循环 ====================

    def _monitor_loop(self):
        """监控循环 - 无差别监听所有按键"""
        utils.log("\n[KeyMonitor] 开始监听所有按键...")
        utils.log("  - 左键、右键、侧键4、侧键5")
        utils.log("  - 业务逻辑由回调处理")

        while not self._stop_event.is_set():
            try:
                # ⭐ 优先检查 F12 退出
                if self.is_key_pressed('f12'):
                    utils.log("[KeyMonitor] 检测到 F12，请求退出")
                    self.app_state.request_exit()
                    break

                # ⭐ 无条件检测所有按键
                for key in ['left', 'right', 'mouse4', 'mouse5']:
                    current_state = self.is_key_pressed(key)
                    last_state = self._last_states[key]

                    # 状态发生变化
                    if current_state != last_state:
                        event = f"{key}_{'press' if current_state else 'release'}"
                        self._trigger_callbacks(event)
                        self._last_states[key] = current_state

                time.sleep(self.poll_interval)

            except Exception as e:
                utils.log(f"[KeyMonitor] 监控错误: {e}")
                import traceback
                traceback.print_exc()
                break

    def _trigger_callbacks(self, event: str):
        """
        触发回调（内部方法）

        Args:
            event: 事件名称
        """
        callbacks = self._callbacks.get(event, [])

        if not callbacks:
            return  # 没有回调则跳过（静默）

        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                utils.log(f"[KeyMonitor] 回调执行失败 ({event}): {e}")
                import traceback
                traceback.print_exc()

    # ==================== 便捷方法（兼容旧接口）====================

    def on_left_press(self, callback: Callable):
        """注册左键按下回调（便捷方法）"""
        self.register_callback('left_press', callback)

    def on_left_release(self, callback: Callable):
        """注册左键释放回调（便捷方法）"""
        self.register_callback('left_release', callback)

    def on_right_press(self, callback: Callable):
        """注册右键按下回调（便捷方法）"""
        self.register_callback('right_press', callback)

    def on_right_release(self, callback: Callable):
        """注册右键释放回调（便捷方法）"""
        self.register_callback('right_release', callback)

    def on_mouse4_press(self, callback: Callable):
        """注册侧键4按下回调（便捷方法）"""
        self.register_callback('mouse4_press', callback)

    def on_mouse4_release(self, callback: Callable):
        """注册侧键4释放回调（便捷方法）"""
        self.register_callback('mouse4_release', callback)

    def on_mouse5_press(self, callback: Callable):
        """注册侧键5按下回调（便捷方法）"""
        self.register_callback('mouse5_press', callback)

    def on_mouse5_release(self, callback: Callable):
        """注册侧键5释放回调（便捷方法）"""
        self.register_callback('mouse5_release', callback)
