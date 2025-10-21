"""驱动级鼠标控制器（纯PID版，带调试信息）"""
import ctypes
import math
import queue as thread_queue
import time
from threading import Thread, Event as ThreadEvent

import win32api
import win32file

import utils
from config import *
from pid_controller import PIDController


class KMouseRequest(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
        ("button_flags", ctypes.c_ubyte)
    ]


class MouseController:
    def __init__(self, device_path=DRIVER_PATH):
        self.driver_handle = None
        self.device_path = device_path
        self.move_queue = thread_queue.Queue(maxsize=2)
        self.mouse_thread = None
        self.stop_event = ThreadEvent()

        # PID控制器
        kp = get_config('PID_KP', 0.35)
        ki = get_config('PID_KI', 0.0)
        kd = get_config('PID_KD', 0.05)
        self.pid = PIDController(kp=kp, ki=ki, kd=kd)

        # 🆕 调试统计
        self.move_count = 0
        self.overshoot_count = 0

        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3

        try:
            self.driver_handle = win32file.CreateFile(
                self.device_path,
                GENERIC_READ | GENERIC_WRITE,
                0, None, OPEN_EXISTING, 0, None
            )
            utils.log(f"[MouseController] ✅ 成功打开驱动")
            utils.log(f"[MouseController] 🎮 PID控制器: Kp={kp}, Ki={ki}, Kd={kd}")

            self.mouse_thread = Thread(target=self._mouse_worker, daemon=True)
            self.mouse_thread.start()

        except win32api.error as e:
            utils.log(f"[MouseController] ❌ 无法打开驱动: {e.winerror}")
            self.close()
            raise

    def _send_mouse_request(self, x, y, button_flags):
        """发送相对鼠标移动"""
        if not self.driver_handle:
            return False

        mouse_req_data = KMouseRequest(x=x, y=y, button_flags=button_flags)
        in_buffer = bytes(mouse_req_data)

        try:
            win32file.DeviceIoControl(self.driver_handle, MOUSE_REQUEST, in_buffer, 0, None)
            return True
        except:
            return False

    def _mouse_worker(self):
        """FPS专用：纯PID控制"""
        utils.log("[MouseController Thread] PID控制模式已启动")

        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        center_x = screen_width // 2
        center_y = screen_height // 2

        try:
            while not self.stop_event.is_set():
                try:
                    move_command = self.move_queue.get(timeout=0.01)
                    target_x, target_y, _, delay_ms, button_flags = move_command
                    current_delay_ms = delay_ms if delay_ms > 0 else DEFAULT_DELAY_MS_PER_STEP

                    self.move_count += 1

                    # 计算误差（偏移）
                    error_x = target_x - center_x
                    error_y = target_y - center_y
                    distance = math.sqrt(error_x**2 + error_y**2)

                    # 🆕 调试：输入信息
                    utils.log(f"\n{'='*50}")
                    utils.log(f"[移动#{self.move_count}] 目标偏移: ({error_x:+.1f}, {error_y:+.1f}) 距离: {distance:.1f}px")

                    # 死区检测
                    if distance < GAME_DEAD_ZONE:
                        utils.log(f"  ✓ 在死区内({distance:.1f} < {GAME_DEAD_ZONE})")
                        self.pid.reset()
                        continue

                    # PID计算
                    move_x_raw, move_y_raw = self.pid.calculate(error_x, error_y)

                    # 🆕 调试：PID输出
                    utils.log(f"  PID输出: ({move_x_raw:+.2f}, {move_y_raw:+.2f})")

                    # 限幅
                    max_single_move = get_config('MAX_SINGLE_MOVE_PX', 25)  # 改为25
                    move_distance = math.sqrt(move_x_raw ** 2 + move_y_raw ** 2)

                    if move_distance > max_single_move:
                        scale = max_single_move / move_distance
                        move_x_raw *= scale
                        move_y_raw *= scale
                        utils.log(f"  ⚡ 限幅: {move_distance:.1f}px -> {max_single_move}px (缩放{scale:.2f})")

                    # 🆕 优化分步逻辑：根据距离动态调整步长
                    max_driver_step = get_config('MAX_DRIVER_STEP_SIZE', 12)

                    # 远距离：大步快移
                    if distance > 50:
                        steps = max(1, int(move_distance / max_driver_step))
                    # 中距离：适中步长
                    elif distance > 20:
                        steps = max(1, int(move_distance / 8))
                    # 近距离：小步精确
                    else:
                        steps = max(1, int(move_distance / 5))

                    step_x = move_x_raw / steps
                    step_y = move_y_raw / steps

                    utils.log(f"  分{steps}步移动, 每步: ({step_x:+.2f}, {step_y:+.2f})")

                    accumulated_x = 0.0
                    accumulated_y = 0.0
                    total_moved_x = 0
                    total_moved_y = 0

                    for i in range(steps):
                        if self.stop_event.is_set():
                            break

                        accumulated_x += step_x
                        accumulated_y += step_y

                        move_x = round(accumulated_x)
                        move_y = round(accumulated_y)

                        accumulated_x -= move_x
                        accumulated_y -= move_y

                        if move_x != 0 or move_y != 0:
                            total_moved_x += move_x
                            total_moved_y += move_y

                            if not self._send_mouse_request(move_x, move_y, APP_MOUSE_NO_BUTTON):
                                break

                        time.sleep(current_delay_ms / 1000.0)

                    # 剩余误差
                    final_move_x = round(accumulated_x)
                    final_move_y = round(accumulated_y)
                    if final_move_x != 0 or final_move_y != 0:
                        total_moved_x += final_move_x
                        total_moved_y += final_move_y
                        self._send_mouse_request(final_move_x, final_move_y, APP_MOUSE_NO_BUTTON)

                    # 🆕 调试：结果分析
                    actual_distance = math.sqrt(total_moved_x**2 + total_moved_y**2)
                    move_error = abs(actual_distance - distance)

                    # 检测过冲：实际移动距离超过目标距离
                    is_overshoot = actual_distance > distance * 1.1  # 超过10%视为过冲
                    if is_overshoot:
                        self.overshoot_count += 1

                    utils.log(f"  实际移动: ({total_moved_x:+d}, {total_moved_y:+d}) 距离: {actual_distance:.1f}px")
                    utils.log(f"  移动误差: {move_error:.1f}px {'⚠️ 过冲!' if is_overshoot else '✓'}")

                    # 🆕 每10次移动输出统计
                    if self.move_count % 10 == 0:
                        overshoot_rate = (self.overshoot_count / self.move_count) * 100
                        utils.log(f"\n📊 统计: 总移动{self.move_count}次, 过冲{self.overshoot_count}次 ({overshoot_rate:.1f}%)")

                    if button_flags != APP_MOUSE_NO_BUTTON:
                        self._send_mouse_request(0, 0, button_flags)

                except thread_queue.Empty:
                    pass

        finally:
            utils.log("[MouseController Thread] 线程已终止")

    def move_to_target(self, target_x, target_y, delay_ms=None, button_flags=APP_MOUSE_NO_BUTTON):
        """移动到目标"""
        if not self.driver_handle or not self.mouse_thread or not self.mouse_thread.is_alive():
            return False

        actual_delay_ms = delay_ms if delay_ms is not None else DEFAULT_DELAY_MS_PER_STEP
        move_command = (target_x, target_y, 0, actual_delay_ms, button_flags)

        while not self.move_queue.empty():
            try:
                self.move_queue.get_nowait()
            except thread_queue.Empty:
                pass

        try:
            self.move_queue.put(move_command, block=False)
            return True
        except:
            return False

    def click(self, button=APP_MOUSE_LEFT_DOWN, delay_ms=50):
        """点击鼠标"""
        if not self.driver_handle:
            return False

        down_flag = button
        up_flag = {
            APP_MOUSE_LEFT_DOWN: APP_MOUSE_LEFT_UP,
            APP_MOUSE_RIGHT_DOWN: APP_MOUSE_RIGHT_UP,
            APP_MOUSE_MIDDLE_DOWN: APP_MOUSE_MIDDLE_UP
        }.get(button)

        if not up_flag:
            return False

        if not self._send_mouse_request(0, 0, down_flag):
            return False
        time.sleep(delay_ms / 1000.0)
        return self._send_mouse_request(0, 0, up_flag)

    def close(self):
        """关闭驱动"""
        if self.driver_handle:
            self.stop_event.set()
            if self.mouse_thread and self.mouse_thread.is_alive():
                self.mouse_thread.join(timeout=2.0)
            win32file.CloseHandle(self.driver_handle)
            self.driver_handle = None
            utils.log("[MouseController] 已关闭")
