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
            self.compensator = None
        else:
            utils.log("[MouseController] ✅ 检测到 1:1 映射环境，无需补偿")

        # 近距 PID 控制器
        kp = get_config("PID_KP", 0.35)
        ki = get_config("PID_KI", 0.0)
        kd = get_config("PID_KD", 0.03)
        self.pid = PIDController(kp=kp, ki=ki, kd=kd)

        # 🔍 调试：打印 PID 参数
        utils.log(f"[MouseController] 🔍 PID 参数: KP={kp}, KI={ki}, KD={kd}")

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
        mickey_x = int(x)
        mickey_y = int(y)

        # 🔍 调试：打印发送给驱动的值
        if mickey_x != 0 or mickey_y != 0:
            utils.log(f"[MouseController] 🔍 发送给驱动: ({mickey_x}, {mickey_y})")

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
        except Exception as e:
            utils.log(f"[MouseController] ❌ 驱动调用失败: {e}")
            return False

    def _mouse_worker(self):
        """主工作线程（纯PID版）"""
        utils.log("[MouseController Thread] 纯PID模式已启动")

        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        center_x = screen_width // 2
        center_y = screen_height // 2

        # 🔍 调试：打印屏幕信息
        utils.log(f"[MouseController] 🔍 屏幕尺寸: {screen_width}x{screen_height}, 中心: ({center_x}, {center_y})")

        dead_zone = get_config("PRECISION_DEAD_ZONE", 2)
        utils.log(f"[MouseController] 🔍 死区: {dead_zone}px")

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

                    # 🔍 调试：打印目标和误差（每10次打印一次，避免刷屏）
                    if self.move_count % 10 == 1:
                        utils.log(
                            f"[MouseController] 🔍 目标: ({target_x}, {target_y}), 误差: ({error_x:.1f}, {error_y:.1f}), 距离: {distance:.1f}px")

                    # 死区判断
                    if distance < dead_zone:
                        if self.move_count % 10 == 1:
                            utils.log(f"[MouseController] 🔍 在死区内，跳过")
                        self.pid.reset()
                        time.sleep(current_delay_ms / 1000.0)
                        continue

                    # 🔧 核心：只用PID计算移动量
                    move_x_raw, move_y_raw = self.pid.calculate(error_x, error_y)


                    # 🔍 调试：打印 PID 输出
                    if self.move_count % 10 == 1:
                        utils.log(f"[MouseController] 🔍 PID 输出: ({move_x_raw:.2f}, {move_y_raw:.2f})")

                    # 🔧 简单限幅（防止单步过大）
                    max_step = get_config("MAX_SINGLE_MOVE_PX", 80)
                    move_norm = math.hypot(move_x_raw, move_y_raw)
                    if move_norm > max_step:
                        scale = max_step / move_norm
                        move_x_raw *= scale
                        move_y_raw *= scale
                        if self.move_count % 10 == 1:
                            utils.log(f"[MouseController] 🔍 限幅: {move_norm:.1f}px → {max_step}px (缩放 {scale:.2f})")

                    move_x = int(round(move_x_raw))
                    move_y = int(round(move_y_raw))

                    # 🔍 调试：打印最终移动值
                    if self.move_count % 10 == 1:
                        utils.log(f"[MouseController] 🔍 最终移动: ({move_x}, {move_y})")

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
        """将目标坐标加入移动队列"""
        # 🔍 调试：打印接收到的目标
        utils.log(f"[MouseController] 🔍 move_to_target 接收: ({target_x}, {target_y})")

        if button_flags is None:
            button_flags = get_config("APP_MOUSE_NO_BUTTON", 0)
        if not self.driver_handle or not self.mouse_thread or not self.mouse_thread.is_alive():
            utils.log("[MouseController] ⚠️ 驱动或线程未就绪")
            return False

        actual_delay_ms = delay_ms if delay_ms is not None else get_config("DEFAULT_DELAY_MS_PER_STEP", 2)
        move_command = (target_x, target_y, 0, actual_delay_ms, button_flags)

        # 🆕 强制覆盖旧指令
        try:
            # 尝试取出旧指令（如果队列已满）
            try:
                old_command = self.move_queue.get_nowait()
                utils.log(f"[MouseController] 🔍 覆盖旧指令: ({old_command[0]}, {old_command[1]})")
            except thread_queue.Empty:
                pass

            # 放入新指令
            self.move_queue.put_nowait(move_command)
            return True
        except thread_queue.Full:
            utils.log("[MouseController] ⚠️ 队列已满（理论上不会发生）")
            return False
        except Exception as e:
            utils.log(f"[MouseController] ❌ 队列操作失败: {e}")
            return False

    def click(self, button=None, delay_ms=50):
        """点击鼠标"""
        utils.log(f"[MouseController] 🔍 执行点击: button={button}, delay={delay_ms}ms")

        if button is None:
            button = get_config("APP_MOUSE_LEFT_DOWN", 1)
        if not self.driver_handle:
            utils.log("[MouseController] ⚠️ 驱动未就绪，点击失败")
            return False

        up_flag = {
            get_config("APP_MOUSE_LEFT_DOWN", 1): get_config("APP_MOUSE_LEFT_UP", 2),
            get_config("APP_MOUSE_RIGHT_DOWN", 4): get_config("APP_MOUSE_RIGHT_UP", 8),
            get_config("APP_MOUSE_MIDDLE_DOWN", 16): get_config("APP_MOUSE_MIDDLE_UP", 32),
        }.get(button)
        if not up_flag:
            utils.log(f"[MouseController] ❌ 未知按钮类型: {button}")
            return False

        if not self._send_mouse_request(0, 0, button):
            return False
        time.sleep(delay_ms / 1000.0)
        return self._send_mouse_request(0, 0, up_flag)

    def close(self):
        """关闭控制器"""
        utils.log("[MouseController] 🔍 开始关闭控制器...")

        if self.driver_handle:
            self.stop_event.set()
            if self.mouse_thread and self.mouse_thread.is_alive():
                utils.log("[MouseController] 🔍 等待工作线程结束...")
                self.mouse_thread.join(timeout=2.0)
            win32file.CloseHandle(self.driver_handle)
            self.driver_handle = None
            utils.log("[MouseController] 已关闭")

        # 🔍 调试：打印最终统计
        utils.log(f"[MouseController] 📊 最终统计: 总移动次数 {self.move_count}")
