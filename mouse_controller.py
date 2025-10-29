# mouse_controller.py
import ctypes
import math
import queue as thread_queue
import time
from threading import Thread, Event as ThreadEvent

import win32api
import win32file

import utils
from config_manager import get_config
from pid_controller import PIDController


class KMouseRequest(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
        ("button_flags", ctypes.c_ubyte),
    ]


class MouseController:
    def __init__(self, device_path=None):
        if device_path is None:
            device_path = get_config("DRIVER_PATH")
        self.driver_handle = None
        self.device_path = device_path
        self.move_queue = thread_queue.Queue(maxsize=1)
        self.mouse_thread = None
        self.stop_event = ThreadEvent()

        # 检查是否需要 Mickey 补偿
        self.use_compensation = self._check_if_compensation_needed()

        if self.use_compensation:
            utils.log("[MouseController] ⚠️ 检测到非 1:1 映射环境，启用补偿器")
            # 这里可以添加补偿器初始化
            self.compensator = None  # 未来如果需要可以添加
        else:
            utils.log("[MouseController] ✅ 检测到 1:1 映射环境，无需补偿")

        # 近距 PID 控制器
        kp = get_config("PID_KP", 0.35)
        ki = get_config("PID_KI", 0.0)
        kd = get_config("PID_KD", 0.03)
        self.pid = PIDController(kp=kp, ki=ki, kd=kd)

        # 统计
        self.move_count = 0
        self.overshoot_count = 0
        self.total_error = 0.0

        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3

        try:
            self.driver_handle = win32file.CreateFile(
                self.device_path,
                GENERIC_READ | GENERIC_WRITE,
                0,
                None,
                OPEN_EXISTING,
                0,
                None,
            )
            utils.log("[MouseController] ✅ 成功打开驱动")
            self.mouse_thread = Thread(target=self._mouse_worker, daemon=True)
            self.mouse_thread.start()
        except win32api.error as e:
            utils.log(f"[MouseController] ❌ 无法打开驱动: {e.winerror}")
            self.close()
            raise

    def _check_if_compensation_needed(self):
        """检查是否需要 Mickey 补偿"""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Control Panel\Mouse",
                0,
                winreg.KEY_READ
            )

            sensitivity, _ = winreg.QueryValueEx(key, "MouseSensitivity")
            speed, _ = winreg.QueryValueEx(key, "MouseSpeed")

            winreg.CloseKey(key)

            # 检查是否在 1:1 映射区间（速度 6-14）且 EPP 关闭
            is_ideal = (6 <= int(sensitivity) <= 14) and (speed == '0')

            if is_ideal:
                utils.log(f"[MouseController] 检测到理想配置: 速度 {sensitivity}/20, EPP 关闭")
            else:
                utils.log(f"[MouseController] 非理想配置: 速度 {sensitivity}/20, EPP {speed}")

            return not is_ideal

        except Exception as e:
            utils.log(f"[MouseController] 无法检测环境设置: {e}，假设需要补偿")
            return True

    def _send_mouse_request(self, x, y, button_flags):
        """发送鼠标移动请求（已优化为 1:1）"""
        if not self.driver_handle:
            return False

        # 在 1:1 映射环境下，直接传递像素值
        # 如果未来需要补偿，在这里添加 compensator 逻辑
        mickey_x = int(x)
        mickey_y = int(y)

        # 安全限幅
        MAX_MICKEY = 500
        mickey_x = max(-MAX_MICKEY, min(mickey_x, MAX_MICKEY))
        mickey_y = max(-MAX_MICKEY, min(mickey_y, MAX_MICKEY))

        mouse_req_data = KMouseRequest(x=mickey_x, y=mickey_y, button_flags=int(button_flags))
        in_buffer = bytes(mouse_req_data)

        try:
            win32file.DeviceIoControl(
                self.driver_handle,
                get_config("MOUSE_REQUEST"),
                in_buffer,
                0,
                None,
            )
            return True
        except Exception:
            return False

    def _compute_far_step(self, err_x: float, err_y: float):
        """远距直驱（极简版，无护栏）"""
        ex, ey = float(err_x), float(err_y)
        dist = math.hypot(ex, ey)

        hybrid_threshold = get_config("HYBRID_MODE_THRESHOLD", 50)

        if dist <= hybrid_threshold:
            return 0, 0, dist

        # 🔧 极简逻辑：直接按比例移动，不削减
        far_gain = get_config("FAR_GAIN", 0.8)  # 80%距离
        step_x = ex * far_gain
        step_y = ey * far_gain

        # 🔧 只保留一个安全上限（防止单步过大）
        max_step = get_config("FAR_MAX_STEP", 120)  # 提高到120px
        step_norm = math.hypot(step_x, step_y)
        if step_norm > max_step:
            scale = max_step / step_norm
            step_x *= scale
            step_y *= scale

        return int(round(step_x)), int(round(step_y)), dist

    def _mouse_worker(self):
        """主工作线程（纯PID版）"""
        utils.log("[MouseController Thread] 纯PID模式已启动")

        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        center_x = screen_width // 2
        center_y = screen_height // 2

        dead_zone = get_config("PRECISION_DEAD_ZONE", 2)

        try:
            while not self.stop_event.is_set():
                try:
                    move_command = self.move_queue.get(timeout=0.01)
                    target_x, target_y, _, delay_ms, button_flags = move_command

                    current_delay_ms = max(1, delay_ms or get_config("DEFAULT_DELAY_MS_PER_STEP", 2))
                    self.move_count += 1

                    # 🔧 简化：直接计算误差
                    error_x = target_x - center_x
                    error_y = target_y - center_y
                    distance = math.hypot(error_x, error_y)

                    # 死区判断
                    if distance < dead_zone:
                        self.pid.reset()
                        time.sleep(current_delay_ms / 1000.0)
                        continue

                    # 🔧 核心：只用PID计算移动量
                    move_x_raw, move_y_raw = self.pid.calculate(error_x, error_y)

                    # 🔧 简单限幅（防止单步过大）
                    max_step = get_config("MAX_SINGLE_MOVE_PX", 80)  # 单步最大80px
                    move_norm = math.hypot(move_x_raw, move_y_raw)
                    if move_norm > max_step:
                        scale = max_step / move_norm
                        move_x_raw *= scale
                        move_y_raw *= scale

                    move_x = int(round(move_x_raw))
                    move_y = int(round(move_y_raw))

                    # 发送移动指令
                    if move_x != 0 or move_y != 0:
                        self._send_mouse_request(move_x, move_y, get_config("APP_MOUSE_NO_BUTTON", 0))

                    time.sleep(current_delay_ms / 1000.0)

                    # 统计
                    if self.move_count % 100 == 0:
                        utils.log(f"📊 统计: 已移动{self.move_count}次")

                    if button_flags != get_config("APP_MOUSE_NO_BUTTON", 0):
                        self._send_mouse_request(0, 0, button_flags)

                except thread_queue.Empty:
                    pass

        finally:
            utils.log("[MouseController Thread] 线程已终止")

    def move_to_target(self, target_x, target_y, delay_ms=None, button_flags=None):

        if button_flags is None:
            button_flags = get_config("APP_MOUSE_NO_BUTTON", 0)
        if not self.driver_handle or not self.mouse_thread or not self.mouse_thread.is_alive():
            return False

        actual_delay_ms = delay_ms if delay_ms is not None else get_config("DEFAULT_DELAY_MS_PER_STEP", 2)
        move_command = (target_x, target_y, 0, actual_delay_ms, button_flags)

        # 🆕 强制覆盖旧指令
        try:
            # 尝试取出旧指令（如果队列已满）
            try:
                self.move_queue.get_nowait()
            except thread_queue.Empty:
                pass

            # 放入新指令（此时队列必定有空间）
            self.move_queue.put_nowait(move_command)
            return True
        except thread_queue.Full:
            # 理论上不会发生（maxsize=1 且已清空）
            return False
        except Exception:
            return False

    def click(self, button=None, delay_ms=50):
        """点击鼠标"""
        if button is None:
            button = get_config("APP_MOUSE_LEFT_DOWN", 1)
        if not self.driver_handle:
            return False

        up_flag = {
            get_config("APP_MOUSE_LEFT_DOWN", 1): get_config("APP_MOUSE_LEFT_UP", 2),
            get_config("APP_MOUSE_RIGHT_DOWN", 4): get_config("APP_MOUSE_RIGHT_UP", 8),
            get_config("APP_MOUSE_MIDDLE_DOWN", 16): get_config("APP_MOUSE_MIDDLE_UP", 32),
        }.get(button)
        if not up_flag:
            return False

        if not self._send_mouse_request(0, 0, button):
            return False
        time.sleep(delay_ms / 1000.0)
        return self._send_mouse_request(0, 0, up_flag)

    def close(self):
        """关闭控制器"""
        if self.driver_handle:
            self.stop_event.set()
            if self.mouse_thread and self.mouse_thread.is_alive():
                self.mouse_thread.join(timeout=2.0)
            win32file.CloseHandle(self.driver_handle)
            self.driver_handle = None
            utils.log("[MouseController] 已关闭")
