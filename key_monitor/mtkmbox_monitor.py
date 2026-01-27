"""MTKmbox 硬件按键监控实现（完整优化版）"""

from typing import Dict, Optional
import time
import threading
import utils
from key_monitor import KeyMonitorBase


class MTKmboxKeyMonitor(KeyMonitorBase):
    """基于 MTKmbox 硬件的按键监控（后台轮询优化）"""

    KEY_NAME_MAP = {
        'left': 'left',
        'right': 'right',
        'middle': 'middle',
        'mouse4': 'x1',
        'mouse5': 'x2',
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
            poll_interval: float = 0.01,
            use_hardware_monitor: bool = True,
            fallback_to_pynput: bool = True
    ):
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

        # ⭐ 后台轮询配置
        self._polling_thread = None
        self._polling_stop = threading.Event()
        self._hardware_polling_interval = 0.010  # 10ms = 100Hz

        from threading import Lock
        self._button_states = {
            'left': False,
            'right': False,
            'middle': False,
            'mouse4': False,
            'mouse5': False,
            'f12': False  # ⭐ 添加 F12 支持
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
                        utils.log("[MTKmboxKeyMonitor] ✅ 使用固件按键监视（后台轮询模式）")
                        self._use_pynput = False

                        # ⭐ 启动后台轮询
                        self._start_hardware_polling()
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

    def _start_hardware_polling(self):
        """⭐ 启动硬件轮询线程"""
        # 确定需要轮询的按键
        keys_to_poll = ['f12']  # ⭐ 始终轮询 F12

        if self.enable_left:
            keys_to_poll.append('left')
        if self.enable_right:
            keys_to_poll.append('right')
        if self.enable_mouse4:
            keys_to_poll.append('mouse4')
        if self.enable_mouse5:
            keys_to_poll.append('mouse5')

        utils.log(f"[MTKmboxKeyMonitor] 启动后台轮询: {keys_to_poll}")
        utils.log(f"[MTKmboxKeyMonitor] 轮询频率: {1000/self._hardware_polling_interval:.0f}Hz")

        self._polling_stop.clear()
        self._polling_thread = threading.Thread(
            target=self._hardware_polling_worker,
            args=(keys_to_poll,),
            daemon=True,
            name="MTKmboxPolling"
        )
        self._polling_thread.start()

    def _hardware_polling_worker(self, keys_to_poll):
        """⭐ 硬件轮询工作线程"""
        utils.log("[MTKmboxKeyMonitor] 轮询线程已启动")

        # ⭐ 性能统计
        poll_count = 0
        start_time = time.time()

        while not self._polling_stop.is_set():
            try:
                if not self.device or not self.device.is_connected():
                    time.sleep(0.1)
                    continue

                # ⭐ 批量查询按键（减少锁竞争）
                new_states = {}

                for key in keys_to_poll:
                    if key == 'f12':
                        # F12 使用 WinAPI（更快）
                        try:
                            import win32api
                            import win32con
                            new_states['f12'] = bool(win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000)
                        except Exception:
                            new_states['f12'] = False
                    else:
                        # 鼠标按键使用固件查询
                        sdk_key = self.KEY_NAME_MAP.get(key, key)
                        state = self.device.get_button_state(sdk_key)
                        new_states[key] = (state == 1)

                # ⭐ 一次性更新所有状态（减少锁开销）
                with self._states_lock:
                    self._button_states.update(new_states)

                # 性能统计
                poll_count += 1
                if poll_count % 1000 == 0:
                    elapsed = time.time() - start_time
                    actual_hz = poll_count / elapsed
                    utils.log(f"[MTKmboxKeyMonitor] 轮询性能: {actual_hz:.1f}Hz (目标: {1000/self._hardware_polling_interval:.0f}Hz)")

                # 休眠
                time.sleep(self._hardware_polling_interval)

            except Exception as e:
                utils.log(f"[MTKmboxKeyMonitor] 轮询异常: {e}")
                time.sleep(0.1)

        utils.log("[MTKmboxKeyMonitor] 轮询线程已退出")

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
        # ⭐ 停止轮询线程
        if self._polling_thread and self._polling_thread.is_alive():
            utils.log("[MTKmboxKeyMonitor] 停止轮询线程...")
            self._polling_stop.set()
            self._polling_thread.join(timeout=2.0)
            if self._polling_thread.is_alive():
                utils.log("[MTKmboxKeyMonitor] ⚠️ 轮询线程未在超时内退出")

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
        """⭐ 检查按键是否按下（从缓存读取，0.001ms）"""
        key = key.lower()

        # ⭐ 统一从缓存读取（包括 F12）
        with self._states_lock:
            return self._button_states.get(key, False)

    def get_button_states(self) -> Dict[str, bool]:
        """⭐ 获取所有按键状态（从缓存读取）"""
        with self._states_lock:
            return self._button_states.copy()
