"""按键监控抽象基类"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Callable
from threading import Thread, Event
import time
import utils


class KeyMonitorBase(ABC):
    """按键监控抽象基类"""

    def __init__(
            self,
            app_state,
            enable_left: bool = False,
            enable_right: bool = True,
            enable_auto_fire: bool = False,
            poll_interval: float = 0.05
    ):
        """
        初始化监控器

        Args:
            app_state: 应用状态对象
            enable_left: 是否监听左键
            enable_right: 是否监听右键
            enable_auto_fire: 是否启用自动开火
            poll_interval: 轮询间隔（秒）
        """
        self.app_state = app_state
        self.enable_left = enable_left
        self.enable_right = enable_right
        self.enable_auto_fire = enable_auto_fire
        self.poll_interval = poll_interval

        # 状态变量
        self._stop_event = Event()
        self._monitor_thread: Optional[Thread] = None
        self._is_running = False

        # 按键状态缓存
        self._last_left_state = False
        self._last_right_state = False

        # 回调函数
        self._on_left_press: Optional[Callable] = None
        self._on_left_release: Optional[Callable] = None
        self._on_right_press: Optional[Callable] = None
        self._on_right_release: Optional[Callable] = None

    # ==================== 抽象方法 ====================

    @abstractmethod
    def is_key_pressed(self, key: str) -> bool:
        """
        检查按键是否按下

        Args:
            key: 按键名称（'left', 'right', 'f12' 等）

        Returns:
            bool: 是否按下

        Note:
            - 子类必须实现此方法
            - 推荐支持的按键：'left', 'right', 'middle', 'mouse4', 'mouse5', 'f12'
        """
        pass  # ✅ 只定义接口，不提供实现

    @abstractmethod
    def get_button_states(self) -> Dict[str, bool]:
        """
        获取所有鼠标按键状态

        Returns:
            Dict[str, bool]: 按键状态字典
                {
                    'left': bool,
                    'right': bool,
                    'middle': bool,
                    'mouse4': bool,
                    'mouse5': bool
                }
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

    # ==================== 公共方法 ====================

    def start(self) -> bool:
        """启动监控"""
        if self._is_running:
            utils.log("[KeyMonitor] 监控已在运行")
            return True

        # 初始化
        if not self._initialize():
            utils.log("[KeyMonitor] 初始化失败")
            return False

        # 启动线程
        self._stop_event.clear()
        self._monitor_thread = Thread(
            target=self._monitor_loop,
            daemon=True,
            name="KeyMonitorThread"
        )
        self._monitor_thread.start()
        self._is_running = True

        # 打印配置信息
        self._print_config()

        utils.log("[KeyMonitor] ✅ 监控已启动")
        return True

    def stop(self):
        """停止监控"""
        if not self._is_running:
            return

        utils.log("[KeyMonitor] ⏳ 正在停止监控...")
        self._stop_event.set()

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
            if self._monitor_thread.is_alive():
                utils.log("[KeyMonitor] ⚠️ 监控线程未在超时内退出")

        self._cleanup()
        self._is_running = False
        utils.log("[KeyMonitor] ✅ 监控已停止")

    def is_running(self) -> bool:
        """检查监控是否运行中"""
        return self._is_running

    # ==================== 回调注册 ====================

    def on_left_press(self, callback: Callable):
        """注册左键按下回调"""
        self._on_left_press = callback

    def on_left_release(self, callback: Callable):
        """注册左键释放回调"""
        self._on_left_release = callback

    def on_right_press(self, callback: Callable):
        """注册右键按下回调"""
        self._on_right_press = callback

    def on_right_release(self, callback: Callable):
        """注册右键释放回调"""
        self._on_right_release = callback

    # ==================== 内部方法 ====================

    def _monitor_loop(self):
        """监控循环（通用逻辑）"""
        utils.log("\n[按键监控] 已启动全局监听")
        utils.log("  F12：退出程序")

        while not self._stop_event.is_set():
            try:
                # 检查 F12 退出
                if self.is_key_pressed('f12'):
                    self.app_state.request_exit()
                    break

                # 左键监控
                if self.enable_left:
                    left_pressed = self.is_key_pressed('left')
                    if left_pressed != self._last_left_state:
                        if left_pressed:
                            self._handle_left_press()
                        else:
                            self._handle_left_release()
                        self._last_left_state = left_pressed

                # 右键监控
                if self.enable_right:
                    right_pressed = self.is_key_pressed('right')
                    if right_pressed != self._last_right_state:
                        if right_pressed:
                            self._handle_right_press()
                        else:
                            self._handle_right_release()
                        self._last_right_state = right_pressed

                time.sleep(self.poll_interval)

            except Exception as e:
                utils.log(f"[KeyMonitor] 监控错误: {e}")
                break

    def _handle_left_press(self):
        """处理左键按下"""
        self.app_state.set_left_pressed(True)
        self.app_state.set_mouse_active(True)
        if self._on_left_press:
            self._on_left_press()

    def _handle_left_release(self):
        """处理左键释放"""
        self.app_state.set_left_pressed(False)
        # 如果右键也未按下，则禁用瞄准
        if not self.enable_right or not self.is_key_pressed('right'):
            self.app_state.set_mouse_active(False)
        if self._on_left_release:
            self._on_left_release()

    def _handle_right_press(self):
        """处理右键按下"""
        self.app_state.set_right_pressed(True)
        self.app_state.set_mouse_active(True)
        if self._on_right_press:
            self._on_right_press()

    def _handle_right_release(self):
        """处理右键释放"""
        self.app_state.set_right_pressed(False)
        # 如果左键也未按下，则禁用瞄准
        if not self.enable_left or not self.is_key_pressed('left'):
            self.app_state.set_mouse_active(False)
        if self._on_right_release:
            self._on_right_release()

    def _print_config(self):
        """打印配置信息"""
        if self.enable_left:
            utils.log("  鼠标左键：按下启用瞄准，释放禁用瞄准")
        if self.enable_right:
            if self.enable_auto_fire:
                utils.log("  鼠标右键：按下启用瞄准并触发自动开火，释放禁用")
            else:
                utils.log("  鼠标右键：按下启用瞄准，释放禁用瞄准")
