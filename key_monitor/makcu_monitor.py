"""Makcu 硬件按键监控实现"""

from typing import Dict
import time
import utils
from makcu import create_controller

from key_monitor import KeyMonitorBase


class MakcuKeyMonitor(KeyMonitorBase):
    """基于 Makcu 硬件的按键监控"""

    def __init__(
            self,
            app_state,
            shared_controller=None,
            enable_left: bool = False,
            enable_right: bool = True,
            enable_mouse4: bool = False,        # ⭐ 新增参数
            enable_mouse5: bool = False,        # ⭐ 新增参数
            enable_auto_fire: bool = False,
            poll_interval: float = 0.05,
            use_hardware_monitor: bool = True,
            fallback_to_pynput: bool = True
    ):
        # ⭐ 调用基类初始化（传递侧键参数）
        super().__init__(
            app_state=app_state,
            enable_left=enable_left,
            enable_right=enable_right,
            enable_mouse4=enable_mouse4,        # ⭐ 传递参数
            enable_mouse5=enable_mouse5,        # ⭐ 传递参数
            enable_auto_fire=enable_auto_fire,
            poll_interval=poll_interval
        )

        self.use_hardware_monitor = use_hardware_monitor
        self.fallback_to_pynput = fallback_to_pynput
        self.controller = shared_controller
        self._is_shared = (shared_controller is not None)
        self.pynput_listener = None
        self._use_pynput = False

        from threading import Lock
        self._button_states = {
            'left': False,
            'right': False,
            'middle': False,
            'mouse4': False,
            'mouse5': False
        }
        self._states_lock = Lock()

    def _initialize(self) -> bool:
        """初始化（支持配置控制）"""
        try:
            utils.log("[MakcuKeyMonitor] 正在初始化...")

            # 获取/创建 Makcu 控制器
            if self._is_shared:
                utils.log("[MakcuKeyMonitor] 使用共享的 Makcu controller")
                if not self.controller or not self.controller.is_connected():
                    utils.log("[MakcuKeyMonitor] 共享 controller 无效或未连接")
                    return False
            else:
                utils.log("[MakcuKeyMonitor] 创建独立的 Makcu controller")
                from config.config_manager import get_config

                port = get_config("MAKCU_PORT", "")
                auto_reconnect = get_config("MAKCU_AUTO_RECONNECT", True)

                self.controller = create_controller(
                    fallback_com_port=port,
                    debug=False,
                    auto_reconnect=auto_reconnect
                )
                time.sleep(0.5)

            # 尝试启用固件监视
            if self.use_hardware_monitor:
                try:
                    utils.log("[MakcuKeyMonitor] 尝试启用固件按键监视...")
                    self.controller.enable_button_monitoring(True)
                    time.sleep(0.3)

                    states = self.controller.get_button_states()
                    if states is not None:
                        utils.log("[MakcuKeyMonitor] 使用固件按键监视")
                        self._use_pynput = False
                        return True
                    else:
                        utils.log("[MakcuKeyMonitor] 固件返回空状态")

                except Exception as e:
                    utils.log(f"[MakcuKeyMonitor] 固件不支持按键监视: {e}")

            # 回退到 pynput
            if self.fallback_to_pynput:
                utils.log("[MakcuKeyMonitor] 降级使用 pynput 物理鼠标监听")
                self._use_pynput = True

                from pynput.mouse import Listener
                self.pynput_listener = Listener(on_click=self._on_pynput_click)
                self.pynput_listener.start()

                utils.log("[MakcuKeyMonitor] pynput 监听已启动")
                return True
            else:
                utils.log("[MakcuKeyMonitor] 配置禁止使用 pynput 回退")
                return False

        except Exception as e:
            utils.log(f"[MakcuKeyMonitor] 初始化失败: {e}")
            return False

    def _on_pynput_click(self, x, y, button, pressed):
        """pynput 点击回调"""
        from pynput.mouse import Button

        button_map = {
            Button.left: 'left',
            Button.right: 'right',
            Button.middle: 'middle',
            Button.x1: 'mouse4',      # 侧键4（后退）
            Button.x2: 'mouse5'       # 侧键5（前进）
        }

        button_name = button_map.get(button)
        if button_name:
            with self._states_lock:
                self._button_states[button_name] = pressed

    def _cleanup(self):
        """清理资源"""
        if self.pynput_listener:
            try:
                utils.log("[MakcuKeyMonitor] 停止 pynput 监听...")
                self.pynput_listener.stop()
                self.pynput_listener = None
            except Exception as e:
                utils.log(f"[MakcuKeyMonitor] pynput 清理失败: {e}")

        if self.controller:
            if not self._is_shared:
                try:
                    utils.log("[MakcuKeyMonitor] 断开 Makcu 连接...")
                    self.controller.disconnect()
                except Exception as e:
                    utils.log(f"[MakcuKeyMonitor] Makcu 断开失败: {e}")
            else:
                utils.log("[MakcuKeyMonitor] 共享模式，跳过断开连接")

            self.controller = None

    def is_key_pressed(self, key: str) -> bool:
        """检查按键是否按下"""
        key = key.lower()

        # F12 特殊处理
        if key == 'f12':
            try:
                import win32api
                import win32con
                return bool(win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000)
            except Exception:
                return False

        # 鼠标按键
        if self._use_pynput:
            with self._states_lock:
                return self._button_states.get(key, False)
        else:
            try:
                if not self.controller:
                    return False

                states = self.controller.get_button_states()
                return states.get(key, False) if states else False
            except Exception as e:
                return False

    def get_button_states(self) -> Dict[str, bool]:
        """获取所有按键状态"""
        if self._use_pynput:
            with self._states_lock:
                return self._button_states.copy()
        else:
            try:
                if not self.controller:
                    return {k: False for k in ['left', 'right', 'middle', 'mouse4', 'mouse5']}

                states = self.controller.get_button_states()
                return states if states else {k: False for k in ['left', 'right', 'middle', 'mouse4', 'mouse5']}
            except Exception:
                return {k: False for k in ['left', 'right', 'middle', 'mouse4', 'mouse5']}
