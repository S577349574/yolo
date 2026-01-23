"""MTKmbox 硬件按键监控实现"""

from typing import Dict, Optional
import time
import utils
from key_monitor import KeyMonitorBase


class MTKmboxKeyMonitor(KeyMonitorBase):
    """基于 MTKmbox 硬件的按键监控"""

    # ⭐ 新增：按键名称映射（基类名称 -> SDK 名称）
    KEY_NAME_MAP = {
        'left': 'left',
        'right': 'right',
        'middle': 'middle',
        'mouse4': 'x1',   # ⭐ 侧键4 -> x1
        'mouse5': 'x2',   # ⭐ 侧键5 -> x2
    }

    def __init__(
            self,
            app_state,
            shared_serial=None,
            enable_left: bool = False,
            enable_right: bool = True,
            enable_mouse4: bool = False,
            enable_mouse5: bool = False,
            enable_auto_fire: bool = False,
            poll_interval: float = 0.01,  # ⭐ 改为 10ms，提高响应速度
            use_hardware_monitor: bool = True,
            fallback_to_pynput: bool = True
    ):
        """
        初始化 MTKmbox 按键监控
        """
        super().__init__(
            app_state=app_state,
            enable_left=enable_left,
            enable_right=enable_right,
            enable_mouse4=enable_mouse4,
            enable_mouse5=enable_mouse5,
            enable_auto_fire=enable_auto_fire,
            poll_interval=poll_interval
        )

        self.use_hardware_monitor = use_hardware_monitor
        self.fallback_to_pynput = fallback_to_pynput
        self.device = shared_serial
        self._is_shared = (shared_serial is not None)
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
        """初始化监控器"""
        try:
            utils.log("[MTKmboxKeyMonitor] 正在初始化...")

            # 获取/创建 MTKmbox 设备
            if self._is_shared:
                utils.log("[MTKmboxKeyMonitor] 使用共享的 MTKmbox 设备")
                if not self.device or not self.device.is_connected():
                    utils.log("[MTKmboxKeyMonitor] ❌ 共享设备无效或未连接")
                    return False
            else:
                utils.log("[MTKmboxKeyMonitor] 创建独立的 MTKmbox 设备")
                from config_manager import get_config
                from mtkmbox import MTKMBOX

                port = get_config("MTKMBOX_PORT", "COM6")
                vid = get_config("MTKMBOX_VID", 0x0416)
                pid = get_config("MTKMBOX_PID", 0x5020)

                self.device = MTKMBOX(port=port, vid=vid, pid=pid, debug=False)
                time.sleep(0.3)

                if not self.device.is_connected():
                    utils.log("[MTKmboxKeyMonitor] ❌ 设备连接失败")
                    return False

            # 尝试使用硬件监视
            if self.use_hardware_monitor:
                try:
                    utils.log("[MTKmboxKeyMonitor] 尝试启用固件按键监视...")

                    # 测试固件按键监视功能
                    test_state = self.device.get_button_state('left')
                    if test_state != -1:
                        utils.log("[MTKmboxKeyMonitor] ✅ 使用固件按键监视")
                        self._use_pynput = False
                        return True
                    else:
                        utils.log("[MTKmboxKeyMonitor] ⚠️ 固件不支持按键监视")

                except Exception as e:
                    utils.log(f"[MTKmboxKeyMonitor] 固件监视初始化失败: {e}")

            # 回退到 pynput
            if self.fallback_to_pynput:
                utils.log("[MTKmboxKeyMonitor] 降级使用 pynput 物理鼠标监听")
                self._use_pynput = True

                from pynput.mouse import Listener
                self.pynput_listener = Listener(on_click=self._on_pynput_click)
                self.pynput_listener.start()

                utils.log("[MTKmboxKeyMonitor] ✅ pynput 监听已启动")
                return True
            else:
                utils.log("[MTKmboxKeyMonitor] ❌ 配置禁止使用 pynput 回退")
                return False

        except Exception as e:
            utils.log(f"[MTKmboxKeyMonitor] ❌ 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _on_pynput_click(self, x, y, button, pressed):
        """pynput 点击回调"""
        from pynput.mouse import Button

        button_map = {
            Button.left: 'left',
            Button.right: 'right',
            Button.middle: 'middle',
            Button.x1: 'mouse4',  # 侧键4（后退）
            Button.x2: 'mouse5'   # 侧键5（前进）
        }

        button_name = button_map.get(button)
        if button_name:
            with self._states_lock:
                self._button_states[button_name] = pressed

    def _cleanup(self):
        """清理资源"""
        # 清理 pynput
        if self.pynput_listener:
            try:
                utils.log("[MTKmboxKeyMonitor] 停止 pynput 监听...")
                self.pynput_listener.stop()
                self.pynput_listener = None
            except Exception as e:
                utils.log(f"[MTKmboxKeyMonitor] pynput 清理失败: {e}")

        # 清理设备连接
        if self.device:
            if not self._is_shared:
                try:
                    utils.log("[MTKmboxKeyMonitor] 断开 MTKmbox 连接...")
                    self.device.close()
                except Exception as e:
                    utils.log(f"[MTKmboxKeyMonitor] 设备断开失败: {e}")
            else:
                utils.log("[MTKmboxKeyMonitor] 共享模式，跳过断开连接")

            self.device = None

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
                if not self.device:
                    return False

                # ⭐ 关键修复：映射按键名称
                sdk_key = self.KEY_NAME_MAP.get(key, key)

                # 调用固件按键查询
                state = self.device.get_button_state(sdk_key)

                # ⭐ 调试日志（可选）
                # utils.log_debug(f"[MTKmbox] {key} -> {sdk_key} = {state}")

                return state == 1  # 1=按下, 0=松开, -1=错误
            except Exception as e:
                utils.log_debug(f"[MTKmboxKeyMonitor] 查询按键失败: {e}")
                return False

    def get_button_states(self) -> Dict[str, bool]:
        """获取所有按键状态"""
        if self._use_pynput:
            with self._states_lock:
                return self._button_states.copy()
        else:
            try:
                if not self.device:
                    return {k: False for k in ['left', 'right', 'middle', 'mouse4', 'mouse5']}

                # ⭐ 查询所有按键（使用映射）
                states = {}
                for key, sdk_key in self.KEY_NAME_MAP.items():
                    state = self.device.get_button_state(sdk_key)
                    states[key] = (state == 1)

                return states
            except Exception as e:
                utils.log_debug(f"[MTKmboxKeyMonitor] 查询状态失败: {e}")
                return {k: False for k in ['left', 'right', 'middle', 'mouse4', 'mouse5']}
