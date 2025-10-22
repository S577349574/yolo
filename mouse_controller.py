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
        kp = get_config('PID_KP', 0.35)  # 基础比例系数
        ki = get_config('PID_KI', 0.0)  # 积分系数
        kd = get_config('PID_KD', 0.03)  # 微分系数
        self.pid = PIDController(kp=kp, ki=ki, kd=kd)

        # 调试统计（计算平均误差）
        self.move_count = 0
        self.overshoot_count = 0
        self.total_error = 0.0  # 累计误差

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
        utils.log("[MouseController Thread] 混合模式已启动 (远直+近增强PID)")

        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        center_x = screen_width // 2
        center_y = screen_height // 2

        hybrid_threshold = get_config('HYBRID_MODE_THRESHOLD', 20)  # 远近距离模式切换阈值
        dead_zone = get_config('PRECISION_DEAD_ZONE', 2)  # 死区大小
        max_driver_step = get_config('MAX_DRIVER_STEP_SIZE', 8)  # 最大驱动步长

        try:
            while not self.stop_event.is_set():
                try:
                    move_command = self.move_queue.get(timeout=0.01)
                    target_x, target_y, _, delay_ms, button_flags = move_command
                    current_delay_ms = max(1, delay_ms if delay_ms > 0 else DEFAULT_DELAY_MS_PER_STEP)

                    self.move_count += 1
                    error_x = target_x - center_x
                    error_y = target_y - center_y
                    distance = math.sqrt(error_x ** 2 + error_y ** 2)

                    # 死区处理
                    if distance < dead_zone:
                        utils.log(f"  ✓ 在死区内({distance:.1f} < {dead_zone}px) - 跳过")
                        self.pid.reset()  # 轻置
                        continue

                    total_moved_x, total_moved_y = 0, 0

                    # 远距离：使用直驱模式
                    if distance > hybrid_threshold:
                        utils.log(f"  🚀 远距直驱模式 (>{hybrid_threshold}px)")
                        # 计算步数：总distance / max_step
                        steps = max(1, int(distance / max_driver_step))
                        step_distance = distance / steps
                        unit_x = error_x / distance  # 单位向量
                        unit_y = error_y / distance

                        for i in range(steps):
                            if self.stop_event.is_set(): break
                            step_x = round(unit_x * step_distance)
                            step_y = round(unit_y * step_distance)
                            if step_x or step_y:
                                total_moved_x += step_x
                                total_moved_y += step_y
                                if not self._send_mouse_request(step_x, step_y, APP_MOUSE_NO_BUTTON):
                                    break
                            time.sleep(current_delay_ms / 1000.0)

                        # 剩余微调：用PID补<1px
                        remain_distance = math.sqrt((error_x - total_moved_x) ** 2 + (error_y - total_moved_y) ** 2)
                        if remain_distance > 1:
                            remain_error_x = error_x - total_moved_x
                            remain_error_y = error_y - total_moved_y
                            fine_x, fine_y = self.pid.calculate(remain_error_x, remain_error_y)
                            self._send_mouse_request(round(fine_x), round(fine_y), APP_MOUSE_NO_BUTTON)

                    else:
                        # 近距离：增强PID
                        utils.log(f"  🎯 近距增强PID模式 (<={hybrid_threshold}px)")
                        move_x_raw, move_y_raw = self.pid.calculate(error_x, error_y)

                        move_distance = math.sqrt(move_x_raw**2 + move_y_raw**2)
                        min_thresh = get_config('MIN_MOVE_THRESHOLD', 0.5)
                        if move_distance < min_thresh:
                            utils.log(f"  ⏭ 微输出({move_distance:.2f}px) - 静默跳过 (防抖)")
                            continue

                        # 动态限幅：预留10% + 基于error
                        max_single = min(get_config('MAX_SINGLE_MOVE_PX', 12), distance * 1.1)
                        if move_distance > max_single:
                            scale = max_single / move_distance
                            move_x_raw *= scale
                            move_y_raw *= scale
                            utils.log(f"  ⚡ 限幅: {move_distance:.1f}px -> {max_single:.1f}px")

                        # 加速：近距离增强，分步计算
                        if distance < 3:
                            steps = 1
                        else:
                            steps = max(1, int(distance / 4))  # 4px/步

                        step_x = move_x_raw / steps
                        step_y = move_y_raw / steps

                        utils.log(f"  分{steps}步加速, 每步: ({step_x:+.2f}, {step_y:+.2f})")

                        accumulated_x = 0.0
                        accumulated_y = 0.0
                        for i in range(steps):
                            if self.stop_event.is_set(): break
                            accumulated_x += step_x
                            accumulated_y += step_y
                            move_x = round(accumulated_x)
                            move_y = round(accumulated_y)
                            accumulated_x -= move_x
                            accumulated_y -= move_y
                            if move_x or move_y:
                                total_moved_x += move_x
                                total_moved_y += move_y
                                self._send_mouse_request(move_x, move_y, APP_MOUSE_NO_BUTTON)
                            time.sleep(max(1, current_delay_ms - 1) / 1000.0)

                        if abs(accumulated_x) >= 0.5 or abs(accumulated_y) >= 0.5:
                            final_x = round(accumulated_x)
                            final_y = round(accumulated_y)
                            total_moved_x += final_x
                            total_moved_y += final_y
                            self._send_mouse_request(final_x, final_y, APP_MOUSE_NO_BUTTON)

                    # 实际移动分析（过冲检测）
                    actual_distance = math.sqrt(total_moved_x ** 2 + total_moved_y ** 2)
                    move_error = abs(actual_distance - distance)
                    self.total_error += move_error
                    is_overshoot = actual_distance > distance * 1.08  # 阈松1.08
                    if is_overshoot:
                        self.overshoot_count += 1
                        self.pid.apply_anti_overshoot(True)  # 假设PID有此方法，或换reset()
                    utils.log(f"  实际移动: ({total_moved_x:+d}, {total_moved_y:+d}) 距离: {actual_distance:.1f}px")
                    utils.log(f"  移动误差: {move_error:.1f}px {'⚠️ 过冲!' if is_overshoot else '✓'}")

                    # 统计（每50次）
                    if self.move_count % 50 == 0:
                        overshoot_rate = (self.overshoot_count / self.move_count) * 100
                        avg_error = self.total_error / self.move_count
                        utils.log(
                            f"\n📊 统计: 总移动{self.move_count}次, 过冲{self.overshoot_count}次 ({overshoot_rate:.1f}%) | 平均误差: {avg_error:.2f}px")

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
