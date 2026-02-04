"""按键监控抽象基类（支持热加载）"""

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
            enable_mouse4: bool = False,
            enable_mouse5: bool = False,
            enable_auto_fire: bool = False,
            poll_interval: float = 0.05
    ):
        """
        初始化监控器

        Args:
            app_state: 应用状态对象
            enable_left: 是否监听左键
            enable_right: 是否监听右键
            enable_mouse4: 是否监听侧键4（后退键）
            enable_mouse5: 是否监听侧键5（前进键）
            enable_auto_fire: 是否启用自动开火
            poll_interval: 轮询间隔（秒）
        """
        self.app_state = app_state
        self.enable_left = enable_left
        self.enable_right = enable_right
        self.enable_mouse4 = enable_mouse4
        self.enable_mouse5 = enable_mouse5
        self.enable_auto_fire = enable_auto_fire
        self.poll_interval = poll_interval

        # 状态变量
        self._stop_event = Event()
        self._monitor_thread: Optional[Thread] = None
        self._is_running = False

        # 按键状态缓存
        self._last_left_state = False
        self._last_right_state = False
        self._last_mouse4_state = False
        self._last_mouse5_state = False

        # 回调函数
        self._on_left_press: Optional[Callable] = None
        self._on_left_release: Optional[Callable] = None
        self._on_right_press: Optional[Callable] = None
        self._on_right_release: Optional[Callable] = None
        self._on_mouse4_press: Optional[Callable] = None
        self._on_mouse4_release: Optional[Callable] = None
        self._on_mouse5_press: Optional[Callable] = None
        self._on_mouse5_release: Optional[Callable] = None

        # ⭐ 注册配置变更回调（支持热加载）
        self._register_config_callbacks()

    # ==================== 配置热加载 ====================

    def _register_config_callbacks(self):
        """注册配置变更回调"""
        try:
            from config_manager import on_config_change

            on_config_change('ENABLE_LEFT_MOUSE_MONITOR', self._on_left_config_change)
            on_config_change('ENABLE_RIGHT_MOUSE_MONITOR', self._on_right_config_change)
            on_config_change('ENABLE_MOUSE4_MONITOR', self._on_mouse4_config_change)
            on_config_change('ENABLE_MOUSE5_MONITOR', self._on_mouse5_config_change)

            utils.log("[KeyMonitor] 已注册配置热加载回调")
        except Exception as e:
            utils.log(f"[KeyMonitor] 配置回调注册失败: {e}")

    def _unregister_config_callbacks(self):
        """取消配置变更回调"""
        try:
            from config_manager import off_config_change

            off_config_change('ENABLE_LEFT_MOUSE_MONITOR', self._on_left_config_change)
            off_config_change('ENABLE_RIGHT_MOUSE_MONITOR', self._on_right_config_change)
            off_config_change('ENABLE_MOUSE4_MONITOR', self._on_mouse4_config_change)
            off_config_change('ENABLE_MOUSE5_MONITOR', self._on_mouse5_config_change)

            utils.log("[KeyMonitor] 已取消配置回调")
        except Exception as e:
            utils.log(f"[KeyMonitor] 配置回调取消失败: {e}")

    def _on_left_config_change(self, new_value):
        """左键配置变更回调"""
        old_value = self.enable_left
        self.enable_left = bool(new_value)

        if old_value != self.enable_left:
            status = "启用" if self.enable_left else "禁用"
            utils.log(f"[KeyMonitor] 左键监控: {status}")

            # 如果禁用时按键正在按下，需要清理状态
            if not self.enable_left and self._last_left_state:
                self._last_left_state = False
                self.app_state.set_left_pressed(False)

    def _on_right_config_change(self, new_value):
        """右键配置变更回调"""
        old_value = self.enable_right
        self.enable_right = bool(new_value)

        if old_value != self.enable_right:
            status = "启用" if self.enable_right else "禁用"
            utils.log(f"[KeyMonitor] 右键监控: {status}")

            if not self.enable_right and self._last_right_state:
                self._last_right_state = False
                self.app_state.set_right_pressed(False)

    def _on_mouse4_config_change(self, new_value):
        """侧键4配置变更回调"""
        old_value = self.enable_mouse4
        self.enable_mouse4 = bool(new_value)

        if old_value != self.enable_mouse4:
            status = "启用" if self.enable_mouse4 else "禁用"
            utils.log(f"[KeyMonitor] 侧键4监控: {status}")

            if not self.enable_mouse4 and self._last_mouse4_state:
                self._last_mouse4_state = False

    def _on_mouse5_config_change(self, new_value):
        """侧键5配置变更回调"""
        old_value = self.enable_mouse5
        self.enable_mouse5 = bool(new_value)

        if old_value != self.enable_mouse5:
            status = "启用" if self.enable_mouse5 else "禁用"
            utils.log(f"[KeyMonitor] 侧键5监控: {status}")

            if not self.enable_mouse5 and self._last_mouse5_state:
                self._last_mouse5_state = False

    # ==================== 抽象方法 ====================

    @abstractmethod
    def is_key_pressed(self, key: str) -> bool:
        """
        检查按键是否按下

        Args:
            key: 按键名称（'left', 'right', 'middle', 'mouse4', 'mouse5', 'f12' 等）

        Returns:
            bool: 是否按下
        """
        pass

    @abstractmethod
    def get_button_states(self) -> Dict[str, bool]:
        """
        获取所有鼠标按键状态

        Returns:
            Dict[str, bool]: 按键状态字典
        """
        pass

    @abstractmethod
    def _initialize(self) -> bool:
        """初始化监控器（子类实现）"""
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

        self._print_config()
        utils.log("[KeyMonitor] 监控已启动")
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

        # ⭐ 取消配置回调
        self._unregister_config_callbacks()

        self._cleanup()
        self._is_running = False
        utils.log("[KeyMonitor] 监控已停止")

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

    def on_mouse4_press(self, callback: Callable):
        """注册侧键4按下回调"""
        self._on_mouse4_press = callback

    def on_mouse4_release(self, callback: Callable):
        """注册侧键4释放回调"""
        self._on_mouse4_release = callback

    def on_mouse5_press(self, callback: Callable):
        """注册侧键5按下回调"""
        self._on_mouse5_press = callback

    def on_mouse5_release(self, callback: Callable):
        """注册侧键5释放回调"""
        self._on_mouse5_release = callback

    # ==================== 内部方法 ====================

    def _monitor_loop(self):
        """监控循环（通用逻辑）"""
        utils.log("\n[按键监控] 已启动全局监听")
        utils.log("  F12：退出程序")
        utils.log("  支持配置热加载（修改配置文件后自动生效）")

        while not self._stop_event.is_set():
            try:
                # 检查 F12 退出
                if self.is_key_pressed('f12'):
                    self.app_state.request_exit()
                    break

                # 左键监控（使用实例变量，由回调更新）
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

                # 侧键4监控
                if self.enable_mouse4:
                    mouse4_pressed = self.is_key_pressed('mouse4')
                    if mouse4_pressed != self._last_mouse4_state:
                        if mouse4_pressed:
                            self._handle_mouse4_press()
                        else:
                            self._handle_mouse4_release()
                        self._last_mouse4_state = mouse4_pressed

                # 侧键5监控
                if self.enable_mouse5:
                    mouse5_pressed = self.is_key_pressed('mouse5')
                    if mouse5_pressed != self._last_mouse5_state:
                        if mouse5_pressed:
                            self._handle_mouse5_press()
                        else:
                            self._handle_mouse5_release()
                        self._last_mouse5_state = mouse5_pressed

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
        """处理左键释放 - 修正版"""
        self.app_state.set_left_pressed(False)
        # 检查是否还有其他任何一个触发键被按住
        still_pressing_any = (
                (self.enable_right and self.is_key_pressed('right')) or
                (self.enable_mouse4 and self.is_key_pressed('mouse4')) or
                (self.enable_mouse5 and self.is_key_pressed('mouse5'))
        )
        if not still_pressing_any:
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
        """处理右键释放 - 修正版"""
        self.app_state.set_right_pressed(False)
        # 检查是否还有其他任何一个触发键被按住
        still_pressing_any = (
                (self.enable_left and self.is_key_pressed('left')) or
                (self.enable_mouse4 and self.is_key_pressed('mouse4')) or
                (self.enable_mouse5 and self.is_key_pressed('mouse5'))
        )
        if not still_pressing_any:
            self.app_state.set_mouse_active(False)

        if self._on_right_release:
            self._on_right_release()

    def _handle_mouse4_press(self):
        """处理侧键4按下"""
        self.app_state.set_mouse_active(True)
        if self._on_mouse4_press:
            self._on_mouse4_press()
        utils.log("[KeyMonitor] 侧键4 按下")

    def _handle_mouse4_release(self):
        """处理侧键4释放"""
        if not (
            (self.enable_left and self.is_key_pressed('left')) or
            (self.enable_right and self.is_key_pressed('right')) or
            (self.enable_mouse5 and self.is_key_pressed('mouse5'))
        ):
            self.app_state.set_mouse_active(False)

        if self._on_mouse4_release:
            self._on_mouse4_release()
        utils.log("[KeyMonitor] 侧键4 释放")

    def _handle_mouse5_press(self):
        """处理侧键5按下"""
        self.app_state.set_mouse_active(True)
        if self._on_mouse5_press:
            self._on_mouse5_press()
        utils.log("[KeyMonitor] 侧键5 按下")

    def _handle_mouse5_release(self):
        """处理侧键5释放"""
        if not (
            (self.enable_left and self.is_key_pressed('left')) or
            (self.enable_right and self.is_key_pressed('right')) or
            (self.enable_mouse4 and self.is_key_pressed('mouse4'))
        ):
            self.app_state.set_mouse_active(False)

        if self._on_mouse5_release:
            self._on_mouse5_release()
        utils.log("[KeyMonitor] 侧键5 释放")

    def _print_config(self):
        """打印配置信息"""
        if self.enable_left:
            utils.log("  鼠标左键：按下启用瞄准，释放禁用瞄准")
        if self.enable_right:
            if self.enable_auto_fire:
                utils.log("  鼠标右键：按下启用瞄准并触发自动开火，释放禁用")
            else:
                utils.log("  鼠标右键：按下启用瞄准，释放禁用瞄准")
        if self.enable_mouse4:
            utils.log("  鼠标侧键4（后退键）：按下启用瞄准，释放禁用瞄准")
        if self.enable_mouse5:
            utils.log("  鼠标侧键5（前进键）：按下启用瞄准，释放禁用瞄准")
