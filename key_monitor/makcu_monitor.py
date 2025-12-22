"""Makcu 硬件按键监控实现"""

from typing import Dict, Optional
import time
import utils
from .base import KeyMonitorBase

# 尝试导入 makcu
try:
    from makcu import create_controller, MouseButton
    MAKCU_AVAILABLE = True
except ImportError:
    MAKCU_AVAILABLE = False
    create_controller = None
    MouseButton = None


class MakcuKeyMonitor(KeyMonitorBase):
    """基于 Makcu 硬件的按键监控"""

    def __init__(
            self,
            app_state,  # ⭐ 第一个位置参数（必须）
            shared_controller=None,  # ⭐ 共享控制器
            enable_left: bool = False,
            enable_right: bool = True,
            enable_auto_fire: bool = False,
            poll_interval: float = 0.05,
            use_hardware_monitor: bool = True,
            fallback_to_pynput: bool = True
    ):
        if not MAKCU_AVAILABLE:
            raise RuntimeError("未安装 makcu 库。请运行: pip install makcu")

        # ⭐ 先调用基类初始化
        super().__init__(
            app_state=app_state,
            enable_left=enable_left,
            enable_right=enable_right,
            enable_auto_fire=enable_auto_fire,
            poll_interval=poll_interval
        )

        # ⭐ 设置 Makcu 特有属性
        self.use_hardware_monitor = use_hardware_monitor
        self.fallback_to_pynput = fallback_to_pynput

        # ⭐ 接收共享实例
        self.controller = shared_controller
        self._is_shared = (shared_controller is not None)

        # 添加调试日志
        if shared_controller:
            utils.log(f"[MakcuKeyMonitor] 接收到共享 controller: {shared_controller}")
            utils.log(
                f"[MakcuKeyMonitor] 已连接: {shared_controller.is_connected() if hasattr(shared_controller, 'is_connected') else 'Unknown'}")
        else:
            utils.log("[MakcuKeyMonitor] 未接收到共享 controller，将创建独立实例")

        self.pynput_listener = None
        self._use_pynput = False

        # 按键状态
        from threading import Lock
        self._button_states = {
            'left': False, 'right': False, 'middle': False,
            'mouse4': False, 'mouse5': False
        }
        self._states_lock = Lock()

    def _initialize(self) -> bool:
        """初始化（支持配置控制）"""
        try:
            utils.log("[MakcuKeyMonitor] 正在初始化...")

            # ========== 1. 获取/创建 Makcu 控制器 ==========
            if self._is_shared:
                # 使用共享实例（已连接）
                utils.log("[MakcuKeyMonitor] 使用共享的 Makcu controller")
                if not self.controller or not self.controller.is_connected():
                    utils.log("[MakcuKeyMonitor] ❌ 共享 controller 无效或未连接")
                    return False
            else:
                # 创建独立实例（独立连接 COM 口）
                utils.log("[MakcuKeyMonitor] 创建独立的 Makcu controller")
                from config_manager import get_config

                port = get_config("MAKCU_PORT", "")
                auto_reconnect = get_config("MAKCU_AUTO_RECONNECT", True)

                self.controller = create_controller(
                    fallback_com_port=port,
                    debug=False,
                    auto_reconnect=auto_reconnect
                )
                time.sleep(0.5)

            # ========== 2. 尝试启用固件监视 ==========
            if self.use_hardware_monitor:
                try:
                    utils.log("[MakcuKeyMonitor] 尝试启用固件按键监视...")
                    self.controller.enable_button_monitoring(True)
                    time.sleep(0.3)

                    # 测试是否真的支持
                    states = self.controller.get_button_states()
                    if states is not None:
                        utils.log("[MakcuKeyMonitor] ✅ 使用固件按键监视")
                        self._use_pynput = False
                        return True
                    else:
                        utils.log("[MakcuKeyMonitor] ⚠️ 固件返回空状态")

                except Exception as e:
                    utils.log(f"[MakcuKeyMonitor] 固件不支持按键监视: {e}")

            # ========== 3. 回退到 pynput ==========
            if self.fallback_to_pynput:
                utils.log("[MakcuKeyMonitor] 降级使用 pynput 物理鼠标监听")
                self._use_pynput = True

                from pynput.mouse import Listener
                self.pynput_listener = Listener(on_click=self._on_pynput_click)
                self.pynput_listener.start()

                utils.log("[MakcuKeyMonitor] ✅ pynput 监听已启动")
                return True
            else:
                utils.log("[MakcuKeyMonitor] ❌ 配置禁止使用 pynput 回退")
                return False

        except Exception as e:
            utils.log(f"[MakcuKeyMonitor] ❌ 初始化失败: {e}")
            return False

    def _on_pynput_click(self, x, y, button, pressed):
        """pynput 点击回调"""
        from pynput.mouse import Button

        button_map = {
            Button.left: 'left',
            Button.right: 'right',
            Button.middle: 'middle',
            Button.x1: 'mouse4',
            Button.x2: 'mouse5'
        }

        button_name = button_map.get(button)
        if button_name:
            with self._states_lock:
                self._button_states[button_name] = pressed

    def _cleanup(self):
        """清理资源"""
        # 清理 pynput 监听器
        if self.pynput_listener:
            try:
                utils.log("[MakcuKeyMonitor] 停止 pynput 监听...")
                self.pynput_listener.stop()
                self.pynput_listener = None
            except Exception as e:
                utils.log(f"[MakcuKeyMonitor] pynput 清理失败: {e}")

        # 清理 Makcu 控制器
        if self.controller:
            # ⭐ 只有非共享模式才断开连接
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

        # F12 特殊处理（使用 WinAPI）
        if key == 'f12':
            try:
                import win32api
                import win32con
                return bool(win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000)
            except Exception:
                return False

        # 鼠标按键
        if self._use_pynput:
            # 使用 pynput 状态
            with self._states_lock:
                return self._button_states.get(key, False)
        else:
            # 使用 Makcu 固件监视
            try:
                if not self.controller:
                    return False

                states = self.controller.get_button_states()
                return states.get(key, False) if states else False
            except Exception as e:
                if hasattr(self, 'debug_mode') and self.debug_mode:
                    utils.log(f"[MakcuKeyMonitor] 获取按键状态失败: {e}")
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
