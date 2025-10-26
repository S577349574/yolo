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
        self.move_queue = thread_queue.Queue(maxsize=2)
        self.mouse_thread = None
        self.stop_event = ThreadEvent()

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

    # ============== 低层发送 ==============
    def _send_mouse_request(self, x, y, button_flags):
        if not self.driver_handle:
            return False
        mouse_req_data = KMouseRequest(x=int(x), y=int(y), button_flags=int(button_flags))
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

    # ============== 远距护栏：单步直驱（加强版） ==============
    def _compute_far_step(self, err_x: float, err_y: float):
        """
        远距直驱护栏（加强版）：
        - 只走一部分误差（FAR_GAIN）
        - 直驱专用步长上限（FAR_MAX_STEP）
        - 禁止一步逼近近距阈值（NEAR_GATE_RATIO * HYBRID_MODE_THRESHOLD）
        - ⭐ 按轴夹紧：防止单轴穿过 0（越线）
        返回：step_x(int), step_y(int), dist(float)
        """
        ex, ey = float(err_x), float(err_y)
        dist = math.hypot(ex, ey)

        hybrid_threshold = get_config("HYBRID_MODE_THRESHOLD", 50)  # 建议：50
        far_gain        = get_config("FAR_GAIN", 0.4)               # 建议：0.4
        far_max_step    = get_config("FAR_MAX_STEP", 12)            # 建议：12
        near_gate_ratio = get_config("NEAR_GATE_RATIO", 0.8)        # 建议：0.8

        if dist <= hybrid_threshold:
            return 0, 0, dist

        # 1) 只走部分误差
        step_x = ex * far_gain
        step_y = ey * far_gain
        step_norm = math.hypot(step_x, step_y)

        # 2) 直驱专用上限
        if step_norm > far_max_step and step_norm > 0:
            scale = far_max_step / step_norm
            step_x *= scale
            step_y *= scale
            step_norm = far_max_step

        # 3) 防过冲缓冲（留出近距余量）
        near_gate = hybrid_threshold * near_gate_ratio  # 例如 50 * 0.8 = 40
        max_allowed = max(dist - near_gate, 0.0)
        if step_norm > max_allowed and step_norm > 0:
            scale = max_allowed / step_norm
            step_x *= scale
            step_y *= scale
            step_norm = max_allowed

        # 4) ⭐ 按轴夹紧：不允许某轴直接穿过 0；预留一定余量防四舍五入穿轴
        axis_gate_px = max(int(hybrid_threshold * 0.25), 3)  # 至少 3px
        # X 轴
        max_ax = max(abs(ex) - axis_gate_px, 0.0)
        if max_ax <= 0:
            step_x = 0.0
        else:
            step_x = max(-max_ax, min(step_x, max_ax))
            if ex > 0 and step_x < 0:
                step_x = 0
            if ex < 0 and step_x > 0:
                step_x = 0
        # Y 轴
        max_ay = max(abs(ey) - axis_gate_px, 0.0)
        if max_ay <= 0:
            step_y = 0.0
        else:
            step_y = max(-max_ay, min(step_y, max_ay))
            if ey > 0 and step_y < 0:
                step_y = 0
            if ey < 0 and step_y > 0:
                step_y = 0

        # 5) 像素化，并避免四舍五入导致跨轴
        rx, ry = int(round(step_x)), int(round(step_y))
        # 再保险：不允许超过“剩余-轴缓冲”
        if abs(rx) > max(int(abs(ex) - axis_gate_px), 0):
            rx = int(math.copysign(max(int(abs(ex) - axis_gate_px), 0), ex))
        if abs(ry) > max(int(abs(ey) - axis_gate_px), 0):
            ry = int(math.copysign(max(int(abs(ey) - axis_gate_px), 0), ey))

        return rx, ry, dist

    # ============== 主工作线程 ==============
    def _mouse_worker(self):
        utils.log("[MouseController Thread] 混合模式已启动 (远直+近增强PID)")

        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        center_x = screen_width // 2
        center_y = screen_height // 2

        hybrid_threshold = get_config("HYBRID_MODE_THRESHOLD", 50)  # 建议：50
        dead_zone = get_config("PRECISION_DEAD_ZONE", 4)
        # 直驱专用上限在 _compute_far_step 内部；保留该值给其他逻辑备用
        max_driver_step = get_config("MAX_DRIVER_STEP_SIZE", 8)

        try:
            while not self.stop_event.is_set():
                try:
                    move_command = self.move_queue.get(timeout=0.01)
                    target_x, target_y, _, delay_ms, button_flags = move_command
                    current_delay_ms = max(
                        1,
                        delay_ms if delay_ms is not None else get_config("DEFAULT_DELAY_MS_PER_STEP", 3),
                    )

                    self.move_count += 1
                    error_x = target_x - center_x
                    error_y = target_y - center_y
                    distance = math.hypot(error_x, error_y)

                    # 死区：轻置 PID 并跳过
                    if distance < dead_zone:
                        utils.log(f"  ✓ 在死区内({distance:.1f} < {dead_zone}px) - 跳过")
                        self.pid.reset()
                        time.sleep(current_delay_ms / 1000.0)
                        continue

                    total_moved_x, total_moved_y = 0, 0

                    # ===== 远距：单步直驱（每帧只发一次小步）=====
                    if distance > hybrid_threshold:
                        utils.log(f"  🚀 远距直驱模式 (>{hybrid_threshold}px)")

                        step_x, step_y, _ = self._compute_far_step(error_x, error_y)
                        if step_x == 0 and step_y == 0:
                            self.pid.reset()
                            time.sleep(current_delay_ms / 1000.0)
                            continue

                        if self._send_mouse_request(step_x, step_y, get_config("APP_MOUSE_NO_BUTTON", 0)):
                            total_moved_x += step_x
                            total_moved_y += step_y

                        time.sleep(current_delay_ms / 1000.0)

                    # ===== 近距：增强 PID =====
                    else:
                        utils.log(f"  🎯 近距增强PID模式 (<= {hybrid_threshold}px)")

                        move_x_raw, move_y_raw = self.pid.calculate(error_x, error_y)
                        move_distance = math.hypot(move_x_raw, move_y_raw)

                        min_thresh = get_config("MIN_MOVE_THRESHOLD", 0.5)
                        if move_distance < min_thresh:
                            utils.log(f"  ⏭ 微输出({move_distance:.2f}px) - 静默跳过 (防抖)")
                            time.sleep(current_delay_ms / 1000.0)
                            continue

                        # 动态限幅（近距）
                        max_single = min(get_config("MAX_SINGLE_MOVE_PX", 12), distance * 1.1)
                        if move_distance > max_single:
                            scale = max_single / move_distance
                            move_x_raw *= scale
                            move_y_raw *= scale
                            utils.log(f"  ⚡ 限幅: {move_distance:.1f}px -> {max_single:.1f}px")

                        # 分步发送（加速感）
                        steps = 1 if distance < 3 else max(1, int(distance / 4))  # ~4px/步
                        step_x = move_x_raw / steps
                        step_y = move_y_raw / steps
                        utils.log(f"  分{steps}步加速, 每步: ({step_x:+.2f}, {step_y:+.2f})")

                        accumulated_x = 0.0
                        accumulated_y = 0.0
                        for _ in range(steps):
                            if self.stop_event.is_set():
                                break

                            accumulated_x += step_x
                            accumulated_y += step_y
                            move_x = round(accumulated_x)
                            move_y = round(accumulated_y)
                            accumulated_x -= move_x
                            accumulated_y -= move_y

                            if move_x or move_y:
                                # ======= 向量范数夹紧（避免一步越过剩余距离-到达缓冲） =======
                                rem_x = error_x - total_moved_x
                                rem_y = error_y - total_moved_y
                                rem_d = math.hypot(rem_x, rem_y)
                                arrival_buffer = max(
                                    get_config("MOUSE_ARRIVAL_THRESHOLD", 5),  # 建议 5
                                    get_config("PRECISION_DEAD_ZONE", 4),
                                )
                                mv_norm = math.hypot(move_x, move_y)
                                max_norm = max(rem_d - arrival_buffer, 0.0)
                                if mv_norm > max_norm and mv_norm > 0:
                                    scale = max_norm / mv_norm
                                    move_x = int(round(move_x * scale))
                                    move_y = int(round(move_y * scale))

                                # ======= ⭐ 按轴夹紧（防止单轴穿线） =======
                                axis_buffer = max(int(arrival_buffer // 2), 2)  # 每轴小缓冲
                                # X 轴
                                if move_x != 0:
                                    allow_x = max(int(abs(rem_x) - axis_buffer), 0)
                                    if abs(move_x) > allow_x:
                                        move_x = int(math.copysign(allow_x, rem_x))
                                # Y 轴
                                if move_y != 0:
                                    allow_y = max(int(abs(rem_y) - axis_buffer), 0)
                                    if abs(move_y) > allow_y:
                                        move_y = int(math.copysign(allow_y, rem_y))
                                # =======================================

                                if move_x or move_y:
                                    total_moved_x += move_x
                                    total_moved_y += move_y
                                    self._send_mouse_request(move_x, move_y, get_config("APP_MOUSE_NO_BUTTON", 0))

                            time.sleep(max(1, current_delay_ms - 1) / 1000.0)

                        # 分数像素补偿（同样做夹紧）
                        if abs(accumulated_x) >= 0.5 or abs(accumulated_y) >= 0.5:
                            final_x = round(accumulated_x)
                            final_y = round(accumulated_y)
                            if final_x or final_y:
                                rem_x = error_x - total_moved_x
                                rem_y = error_y - total_moved_y
                                rem_d = math.hypot(rem_x, rem_y)
                                arrival_buffer = max(
                                    get_config("MOUSE_ARRIVAL_THRESHOLD", 5),
                                    get_config("PRECISION_DEAD_ZONE", 4),
                                )
                                mv_norm = math.hypot(final_x, final_y)
                                max_norm = max(rem_d - arrival_buffer, 0.0)
                                if mv_norm > max_norm and mv_norm > 0:
                                    scale = max_norm / mv_norm
                                    final_x = int(round(final_x * scale))
                                    final_y = int(round(final_y * scale))

                                # ⭐ 分数像素补偿也做按轴夹紧
                                axis_buffer = max(int(arrival_buffer // 2), 2)
                                if final_x != 0:
                                    allow_x = max(int(abs(rem_x) - axis_buffer), 0)
                                    if abs(final_x) > allow_x:
                                        final_x = int(math.copysign(allow_x, rem_x))
                                if final_y != 0:
                                    allow_y = max(int(abs(rem_y) - axis_buffer), 0)
                                    if abs(final_y) > allow_y:
                                        final_y = int(math.copysign(allow_y, rem_y))

                                if final_x or final_y:
                                    total_moved_x += final_x
                                    total_moved_y += final_y
                                    self._send_mouse_request(final_x, final_y, get_config("APP_MOUSE_NO_BUTTON", 0))

                    # ===== 统计与过冲检测 =====
                    actual_distance = math.hypot(total_moved_x, total_moved_y)
                    move_error = abs(actual_distance - distance)
                    self.total_error += move_error

                    is_overshoot = actual_distance > distance * 1.08
                    if is_overshoot:
                        self.overshoot_count += 1
                        try:
                            self.pid.apply_anti_overshoot(True)
                        except AttributeError:
                            self.pid.reset()

                    utils.log(
                        f"  实际移动: ({total_moved_x:+d}, {total_moved_y:+d}) 距离: {actual_distance:.1f}px"
                    )
                    utils.log(f"  移动误差: {move_error:.1f}px {'⚠️ 过冲!' if is_overshoot else '✓'}")

                    if self.move_count % 50 == 0:
                        overshoot_rate = (self.overshoot_count / self.move_count) * 100
                        avg_error = self.total_error / self.move_count
                        utils.log(
                            f"\n📊 统计: 总移动{self.move_count}次, 过冲{self.overshoot_count}次 "
                            f"({overshoot_rate:.1f}%) | 平均误差: {avg_error:.2f}px"
                        )

                    if button_flags != get_config("APP_MOUSE_NO_BUTTON", 0):
                        self._send_mouse_request(0, 0, button_flags)

                except thread_queue.Empty:
                    pass

        finally:
            utils.log("[MouseController Thread] 线程已终止")

    # ============== 对外接口 ==============
    def move_to_target(self, target_x, target_y, delay_ms=None, button_flags=None):
        if button_flags is None:
            button_flags = get_config("APP_MOUSE_NO_BUTTON", 0)
        if not self.driver_handle or not self.mouse_thread or not self.mouse_thread.is_alive():
            return False

        actual_delay_ms = delay_ms if delay_ms is not None else get_config("DEFAULT_DELAY_MS_PER_STEP", 3)
        move_command = (target_x, target_y, 0, actual_delay_ms, button_flags)

        # 仅保留最新命令，降低滞后
        while not self.move_queue.empty():
            try:
                self.move_queue.get_nowait()
            except thread_queue.Empty:
                break

        try:
            self.move_queue.put(move_command, block=False)
            return True
        except Exception:
            return False

    def click(self, button=None, delay_ms=50):
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
        if self.driver_handle:
            self.stop_event.set()
            if self.mouse_thread and self.mouse_thread.is_alive():
                self.mouse_thread.join(timeout=2.0)
            win32file.CloseHandle(self.driver_handle)
            self.driver_handle = None
            utils.log("[MouseController] 已关闭")
