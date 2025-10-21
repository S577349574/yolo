"""驱动级鼠标控制器"""
import ctypes
import math
import queue as thread_queue
import time
from threading import Thread, Event as ThreadEvent

import win32api
import win32file

import utils
from config import *


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
        self.move_queue = thread_queue.Queue(maxsize=3)  # 增加队列大小到3，缓冲命令减少延迟
        self.mouse_thread = None
        self.stop_event = ThreadEvent()

        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3

        try:
            self.driver_handle = win32file.CreateFile(
                self.device_path,
                GENERIC_READ | GENERIC_WRITE,
                0, None, OPEN_EXISTING, 0, None
            )
            utils.log(f"[MouseController] 成功打开驱动 '{self.device_path}'")

            self.mouse_thread = Thread(target=self._mouse_worker, daemon=True)
            self.mouse_thread.start()
            utils.log(f"[MouseController] 鼠标线程已启动（游戏模式:{'开启' if GAME_MODE else '关闭'}）")

        except win32api.error as e:
            utils.log(f"[MouseController] ERROR: 无法打开驱动。错误码: {e.winerror}")
            self.close()
            raise

    def _send_mouse_request(self, x, y, button_flags):
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
        utils.log("[MouseController Thread] 线程已启动")
        try:
            while not self.stop_event.is_set():
                try:
                    move_command = self.move_queue.get(timeout=0.01)
                    target_x, target_y, _, delay_ms, button_flags = move_command
                    current_delay_ms = delay_ms if delay_ms > 0 else DEFAULT_DELAY_MS_PER_STEP

                    # ===== 游戏模式 =====
                    if GAME_MODE:
                        screen_width = win32api.GetSystemMetrics(0)
                        screen_height = win32api.GetSystemMetrics(1)
                        center_x = screen_width // 2
                        center_y = screen_height // 2

                        # 计算浮点偏移，保持精度
                        offset_x = (target_x - center_x) * GAME_DAMPING_FACTOR
                        offset_y = (target_y - center_y) * GAME_DAMPING_FACTOR

                        # 动态阻尼（如果启用）
                        distance = math.sqrt(offset_x ** 2 + offset_y ** 2)
                        # 死区检测
                        if abs(offset_x) < GAME_DEAD_ZONE and abs(offset_y) < GAME_DEAD_ZONE:
                            utils.log(f"[DEBUG] ⚠️ 死区触发，跳过移动")
                            continue

                        # 步长计算，确保最小速度
                        min_pixels_per_step = 2  # 最小每步像素，确保速度
                        steps = max(1, int(distance / max(MOUSE_MAX_PIXELS_PER_STEP, min_pixels_per_step)))
                        step_x = offset_x / steps
                        step_y = offset_y / steps

                        # 如果步长太小，强制单步完成
                        if steps == 1 and (abs(step_x) < min_pixels_per_step or abs(step_y) < min_pixels_per_step):
                            final_move_x = round(offset_x)
                            final_move_y = round(offset_y)
                            if final_move_x != 0 or final_move_y != 0:
                                self._send_mouse_request(final_move_x, final_move_y, APP_MOUSE_NO_BUTTON)
                            continue

                        # 误差累积
                        accumulated_x = 0.0
                        accumulated_y = 0.0
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
                                # 日志增强：监控发送像素
                                utils.log(f"发送像素: dx={move_x}, dy={move_y} | 预期剩余: {distance:.1f}px")
                                if not self._send_mouse_request(move_x, move_y, APP_MOUSE_NO_BUTTON):
                                    break
                            time.sleep(current_delay_ms / 1000.0)

                        # 发送剩余误差，确保总像素精确
                        final_move_x = round(accumulated_x)
                        final_move_y = round(accumulated_y)
                        if final_move_x != 0 or final_move_y != 0:
                            utils.log(f"剩余像素: dx={final_move_x}, dy={final_move_y} | 预期剩余: {distance:.1f}px")
                            self._send_mouse_request(final_move_x, final_move_y, APP_MOUSE_NO_BUTTON)

                        if button_flags != APP_MOUSE_NO_BUTTON:
                            self._send_mouse_request(0, 0, button_flags)

                    # ===== 桌面模式 =====
                    else:
                        while not self.stop_event.is_set():
                            actual_x, actual_y = win32api.GetCursorPos()
                            remaining_dx = target_x - actual_x
                            remaining_dy = target_y - actual_y
                            distance = math.sqrt(remaining_dx ** 2 + remaining_dy ** 2)

                            if distance <= MOUSE_ARRIVAL_THRESHOLD:
                                if remaining_dx != 0 or remaining_dy != 0 or button_flags != APP_MOUSE_NO_BUTTON:
                                    self._send_mouse_request(remaining_dx, remaining_dy, button_flags)
                                break

                            step_dx = round(remaining_dx * MOUSE_PROPORTIONAL_FACTOR)
                            step_dy = round(remaining_dy * MOUSE_PROPORTIONAL_FACTOR)

                            if step_dx == 0 and remaining_dx != 0:
                                step_dx = 1 if remaining_dx > 0 else -1
                            if step_dy == 0 and remaining_dy != 0:
                                step_dy = 1 if remaining_dy > 0 else -1

                            current_step_distance = math.sqrt(step_dx ** 2 + step_dy ** 2)
                            if current_step_distance > MOUSE_MAX_PIXELS_PER_STEP:
                                scale_factor = MOUSE_MAX_PIXELS_PER_STEP / current_step_distance
                                step_dx = round(step_dx * scale_factor)
                                step_dy = round(step_dy * scale_factor)

                            if step_dx != 0 or step_dy != 0:
                                if not self._send_mouse_request(step_dx, step_dy, APP_MOUSE_NO_BUTTON):
                                    break
                            time.sleep(current_delay_ms / 1000.0)

                except thread_queue.Empty:
                    pass
        finally:
            utils.log("[MouseController Thread] 线程已终止")

    def move_to_absolute(self, target_x, target_y, num_steps=None, delay_ms=None,
                         button_flags=APP_MOUSE_NO_BUTTON):
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
        if self.driver_handle:
            self.stop_event.set()
            if self.mouse_thread and self.mouse_thread.is_alive():
                self.mouse_thread.join(timeout=2.0)
            win32file.CloseHandle(self.driver_handle)
            self.driver_handle = None
            utils.log("[MouseController] 已关闭")
