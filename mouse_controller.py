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

        # 🆕 预计算所有常量和配置
        self.screen_width = win32api.GetSystemMetrics(0)
        self.screen_height = win32api.GetSystemMetrics(1)
        self.center_x = self.screen_width // 2
        self.center_y = self.screen_height // 2

        dead_zone = get_config("PRECISION_DEAD_ZONE", 2)
        self.dead_zone_sq = dead_zone * dead_zone
        self.max_step = get_config("MAX_SINGLE_MOVE_PX", 80)
        self.max_step_sq = self.max_step * self.max_step

        # 时间转换常量
        self.ms_to_sec = 0.001
        self.default_delay_sec = get_config("DEFAULT_DELAY_MS_PER_STEP", 2) * self.ms_to_sec

        # 按钮标志
        self.no_button_flag = get_config("APP_MOUSE_NO_BUTTON", 0)
        self.button_up_map = {
            get_config("APP_MOUSE_LEFT_DOWN", 1): get_config("APP_MOUSE_LEFT_UP", 2),
            get_config("APP_MOUSE_RIGHT_DOWN", 4): get_config("APP_MOUSE_RIGHT_UP", 8),
            get_config("APP_MOUSE_MIDDLE_DOWN", 16): get_config("APP_MOUSE_MIDDLE_UP", 32),
        }

        # IOCTL 代码
        self.mouse_request_code = get_config("MOUSE_REQUEST")

        # 调试模式
        self.debug_mode = get_config("DEBUG_MODE", False)

        # 🆕 重用结构体对象
        self.mouse_req = KMouseRequest()

        # 检查是否需要 Mickey 补偿
        self.use_compensation = self._check_if_compensation_needed()

        if self.use_compensation:
            utils.log("[MouseController] 检测到非 1:1 映射环境，启用补偿器")
            self.compensator = None
        else:
            utils.log("[MouseController] 检测到 1:1 映射环境，无需补偿")

        # 近距 PID 控制器
        kp = get_config("PID_KP", 0.35)
        ki = get_config("PID_KI", 0.0)
        kd = get_config("PID_KD", 0.03)
        self.pid = PIDController(kp=kp, ki=ki, kd=kd)

        if self.debug_mode:
            utils.log(f"[MouseController] PID 参数: KP={kp}, KI={ki}, KD={kd}")
            utils.log(
                f"[MouseController] 屏幕尺寸: {self.screen_width}x{self.screen_height}, 中心: ({self.center_x}, {self.center_y})")
            utils.log(f"[MouseController] 死区: {math.sqrt(self.dead_zone_sq):.1f}px (平方: {self.dead_zone_sq})")

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
            utils.log("[MouseController] 成功打开驱动")
            self.mouse_thread = Thread(target=self._mouse_worker, daemon=True)
            self.mouse_thread.start()
        except win32api.error as e:
            utils.log(f"[MouseController] 无法打开驱动: {e.winerror}")
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

        # 安全限幅
        MAX_MICKEY = 500
        if mickey_x > MAX_MICKEY:
            mickey_x = MAX_MICKEY
        elif mickey_x < -MAX_MICKEY:
            mickey_x = -MAX_MICKEY

        if mickey_y > MAX_MICKEY:
            mickey_y = MAX_MICKEY
        elif mickey_y < -MAX_MICKEY:
            mickey_y = -MAX_MICKEY

        # 🆕 重用结构体对象
        self.mouse_req.x = mickey_x
        self.mouse_req.y = mickey_y
        self.mouse_req.button_flags = int(button_flags)
        in_buffer = bytes(self.mouse_req)

        try:
            win32file.DeviceIoControl(
                self.driver_handle,
                self.mouse_request_code,
                in_buffer,
                0,
                None,
            )
            return True
        except Exception as e:
            utils.log(f"[MouseController] 驱动调用失败: {e}")
            return False

    def _mouse_worker(self):
        """主工作线程（纯PID版 - 性能优化）"""
        utils.log("[MouseController Thread] 纯PID模式已启动")

        try:
            while not self.stop_event.is_set():
                try:
                    move_command = self.move_queue.get(timeout=0.01)
                    target_x, target_y, _, delay_ms, button_flags = move_command

                    # 🆕 使用预计算的延迟
                    sleep_time = (delay_ms * self.ms_to_sec) if delay_ms else self.default_delay_sec
                    self.move_count += 1

                    # 🆕 快速距离检查（避免开方）
                    error_x = target_x - self.center_x
                    error_y = target_y - self.center_y
                    distance_sq = error_x * error_x + error_y * error_y

                    # 死区判断
                    if distance_sq < self.dead_zone_sq:
                        if self.debug_mode and self.move_count % 10 == 1:
                            utils.log("[MouseController] 在死区内，跳过")
                        self.pid.reset()
                        time.sleep(sleep_time)
                        continue

                    # PID 计算
                    move_x_raw, move_y_raw = self.pid.calculate(error_x, error_y)

                    # 🆕 快速限幅检查（避免开方）
                    move_sq = move_x_raw * move_x_raw + move_y_raw * move_y_raw
                    if move_sq > self.max_step_sq:
                        scale = self.max_step / math.sqrt(move_sq)
                        move_x_raw *= scale
                        move_y_raw *= scale
                        if self.debug_mode and self.move_count % 10 == 1:
                            utils.log(
                                f"[MouseController] 限幅: {math.sqrt(move_sq):.1f}px → {self.max_step}px (缩放 {scale:.2f})")

                    # 🆕 快速四舍五入
                    move_x = int(move_x_raw + 0.5 if move_x_raw > 0 else move_x_raw - 0.5)
                    move_y = int(move_y_raw + 0.5 if move_y_raw > 0 else move_y_raw - 0.5)

                    # 发送移动指令（使用位运算检查）
                    if move_x | move_y:  # 比 move_x != 0 or move_y != 0 稍快
                        self._send_mouse_request(move_x, move_y, self.no_button_flag)

                    time.sleep(sleep_time)

                    if button_flags != self.no_button_flag:
                        self._send_mouse_request(0, 0, button_flags)

                except thread_queue.Empty:
                    pass

        finally:
            utils.log("[MouseController Thread] 线程已终止")

    def move_to_target(self, target_x, target_y, delay_ms=None, button_flags=None):
        """将目标坐标加入移动队列"""
        if button_flags is None:
            button_flags = self.no_button_flag

        if not self.driver_handle or not self.mouse_thread or not self.mouse_thread.is_alive():
            utils.log("[MouseController] ⚠驱动或线程未就绪")
            return False

        actual_delay_ms = delay_ms if delay_ms is not None else get_config("DEFAULT_DELAY_MS_PER_STEP", 2)
        move_command = (target_x, target_y, 0, actual_delay_ms, button_flags)

        # 🆕 优化队列操作
        if self.move_queue.full():
            try:
                old_command = self.move_queue.get_nowait()
                if self.debug_mode:
                    utils.log(f"[MouseController] 覆盖旧指令: ({old_command[0]}, {old_command[1]})")
            except thread_queue.Empty:
                pass

        try:
            self.move_queue.put_nowait(move_command)
            return True
        except thread_queue.Full:
            if self.debug_mode:
                utils.log("[MouseController] 队列已满（理论上不会发生）")
            return False
        except Exception as e:
            utils.log(f"[MouseController] 队列操作失败: {e}")
            return False

    def click(self, button=None, delay_ms=50):
        """点击鼠标"""
        if self.debug_mode:
            utils.log(f"[MouseController] 执行点击: button={button}, delay={delay_ms}ms")

        if button is None:
            button = get_config("APP_MOUSE_LEFT_DOWN", 1)

        if not self.driver_handle:
            utils.log("[MouseController] ⚠驱动未就绪，点击失败")
            return False

        # 🆕 使用预计算的按钮映射
        up_flag = self.button_up_map.get(button)
        if not up_flag:
            utils.log(f"[MouseController] 未知按钮类型: {button}")
            return False

        if not self._send_mouse_request(0, 0, button):
            return False
        time.sleep(delay_ms * self.ms_to_sec)
        return self._send_mouse_request(0, 0, up_flag)

    def close(self):
        """关闭控制器"""
        utils.log("[MouseController] 开始关闭控制器...")

        if self.driver_handle:
            self.stop_event.set()
            if self.mouse_thread and self.mouse_thread.is_alive():
                utils.log("[MouseController] 等待工作线程结束...")
                self.mouse_thread.join(timeout=2.0)
            win32file.CloseHandle(self.driver_handle)
            self.driver_handle = None
            utils.log("[MouseController] 已关闭")

        if self.debug_mode:
            utils.log(f"[MouseController] 最终统计: 总移动次数 {self.move_count}")
