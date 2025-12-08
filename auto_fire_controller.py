# auto_fire_controller.py
"""自动开火与压枪控制器（适配新版鼠标控制器接口 + XY双轴压枪）"""

import threading
import time
from typing import List, Optional

import win32api

import utils
from config_manager import get_config


class AutoFireController:
    """自动开火控制器（含压枪功能 - 支持手动/自动两种模式 + XY双轴）"""

    def __init__(self, mouse_controller):
        self.mouse_controller = mouse_controller

        # 状态锁
        self._lock = threading.Lock()

        # 射击状态（自动开火模式）
        self.is_firing = False
        self.fire_start_time = 0.0
        self.shot_count = 0

        # 准确率跟踪
        self.recent_errors: List[float] = []
        self.max_error_history = 30

        # 🔥 压枪状态（XY双轴）
        self.total_offset_x = 0.0
        self.total_offset_y = 0.0
        self.last_recoil_time = 0.0
        self.accumulated_offset_x = 0.0
        self.accumulated_offset_y = 0.0

        # 性能优化
        self.last_log_time = 0.0
        self.log_interval = 1.0
        self.debug_mode = get_config('AUTO_FIRE_DEBUG_MODE', False)
        self.debug_counter = 0

        # 🆕 手动压枪模式
        self.manual_recoil_active = False
        self.manual_recoil_thread: Optional[threading.Thread] = None
        self.manual_recoil_stop_flag = False

    # ==================== 适配新接口的辅助方法 ====================

    def _send_move(self, dx: int, dy: int) -> bool:
        """发送鼠标移动（适配新接口）"""
        if hasattr(self.mouse_controller, '_send_move'):
            # 新接口
            return self.mouse_controller._send_move(dx, dy)
        elif hasattr(self.mouse_controller, '_send_mouse_request'):
            # 旧接口兼容
            no_button = get_config('APP_MOUSE_NO_BUTTON', 0)
            return self.mouse_controller._send_mouse_request(dx, dy, no_button)
        else:
            utils.log("⚠ 鼠标控制器接口不兼容")
            return False

    def _send_button(self, button_flags: int) -> bool:
        """发送鼠标按钮（适配新接口）"""
        if hasattr(self.mouse_controller, '_send_button'):
            # 新接口
            return self.mouse_controller._send_button(button_flags)
        elif hasattr(self.mouse_controller, '_send_mouse_request'):
            # 旧接口兼容
            return self.mouse_controller._send_mouse_request(0, 0, button_flags)
        else:
            utils.log("⚠ 鼠标控制器接口不兼容")
            return False

    def _send_move_with_button(self, dx: int, dy: int, button_flags: int) -> bool:
        """同时发送移动和按钮（适配新接口）"""
        if hasattr(self.mouse_controller, '_send_mouse_request'):
            # 旧接口：单次调用
            return self.mouse_controller._send_mouse_request(dx, dy, button_flags)
        else:
            # 新接口：分两次调用
            result = True
            if dx != 0 or dy != 0:
                result = self._send_move(dx, dy)
            if button_flags != 0:
                result = self._send_button(button_flags) and result
            return result

    # ==================== 准确率跟踪 ====================

    def update_accuracy(self, error_distance: float) -> float:
        """更新准确率（基于误差距离）"""
        with self._lock:
            self.recent_errors.append(error_distance)

            if len(self.recent_errors) > self.max_error_history:
                self.recent_errors.pop(0)

            if not self.recent_errors:
                return 0.0

            avg_error = sum(self.recent_errors) / len(self.recent_errors)
            base_error = 10.0
            accuracy = 1.0 / (1.0 + avg_error / base_error)

            return accuracy

    def should_auto_fire(
            self,
            target_locked: bool,
            lock_frames: int,
            current_accuracy: float,
            error_distance: float
    ) -> bool:
        """判断是否应该自动开火"""
        if not get_config('ENABLE_AUTO_FIRE', False):
            return False

        if not target_locked:
            return False

        min_lock_frames = get_config('AUTO_FIRE_MIN_LOCK_FRAMES', 3)
        if lock_frames < min_lock_frames:
            return False

        accuracy_threshold = get_config('AUTO_FIRE_ACCURACY_THRESHOLD', 0.75)
        if current_accuracy < accuracy_threshold:
            return False

        distance_threshold = get_config('AUTO_FIRE_DISTANCE_THRESHOLD', 20.0)
        if error_distance > distance_threshold:
            return False

        return True

    # ==================== 自动开火模式 ====================

    def start_firing(self) -> None:
        """开始射击（按下左键 - 自动开火模式）"""
        with self._lock:
            if self.is_firing:
                return

            self.is_firing = True
            self.fire_start_time = time.time()
            self.last_recoil_time = time.time()
            self.total_offset_x = 0.0
            self.total_offset_y = 0.0
            self.accumulated_offset_x = 0.0
            self.accumulated_offset_y = 0.0
            self.shot_count = 0
            self.debug_counter = 0

            current_time = time.time()
            if current_time - self.last_log_time > self.log_interval:
                utils.log("开始自动射击")
                self.last_log_time = current_time

            # ⭐ 使用适配方法
            left_down = get_config('APP_MOUSE_LEFT_DOWN', 1)
            self._send_button(left_down)

    def stop_firing(self) -> None:
        """停止射击（释放左键 - 自动开火模式）"""
        with self._lock:
            if not self.is_firing:
                return

            self.is_firing = False
            fire_duration = time.time() - self.fire_start_time

            # ⭐ 使用适配方法
            left_up = get_config('APP_MOUSE_LEFT_UP', 2)
            self._send_button(left_up)

            # 计算 XY 双轴速度
            actual_speed_x = self.total_offset_x / fire_duration if fire_duration > 0 else 0
            actual_speed_y = self.total_offset_y / fire_duration if fire_duration > 0 else 0
            theoretical_speed_x = get_config('RECOIL_HORIZONTAL_SPEED', 0.0)
            theoretical_speed_y = get_config('RECOIL_VERTICAL_SPEED', 150.0)

            current_time = time.time()
            if current_time - self.last_log_time > self.log_interval:
                utils.log(
                    f"停止射击 | 持续: {fire_duration:.2f}s | 子弹: {self.shot_count} | "
                    f"累积: X={self.total_offset_x:+.1f}px Y={self.total_offset_y:+.1f}px | "
                    f"速度: X={actual_speed_x:+.1f}/{theoretical_speed_x:+.1f} "
                    f"Y={actual_speed_y:.1f}/{theoretical_speed_y:.1f} px/s"
                )
                self.last_log_time = current_time

            self.total_offset_x = 0.0
            self.total_offset_y = 0.0
            self.accumulated_offset_x = 0.0
            self.accumulated_offset_y = 0.0
            self.shot_count = 0

    def apply_recoil_control(self) -> None:
        """应用压枪偏移（自动开火模式 - XY双轴累积发送版本）"""
        if not get_config('ENABLE_RECOIL_CONTROL', True) or not self.is_firing:
            return

        with self._lock:
            current_time = time.time()
            delta_time = current_time - self.last_recoil_time

            min_delta = 0.001
            if delta_time < min_delta:
                return

            self.last_recoil_time = current_time
            self.shot_count += 1

            pattern = get_config('RECOIL_PATTERN', 'linear')

            # 获取 XY 双轴偏移
            if pattern == 'linear':
                offset_x, offset_y = self._calculate_linear_recoil(delta_time)
            elif pattern == 'exponential':
                offset_x, offset_y = self._calculate_exponential_recoil(delta_time)
            elif pattern == 'custom':
                offset_x, offset_y = self._calculate_custom_recoil()
            else:
                offset_x, offset_y = self._calculate_linear_recoil(delta_time)

            # 双轴独立限幅
            max_single_move_x = get_config('RECOIL_MAX_SINGLE_MOVE_X', 50.0)
            max_single_move_y = get_config('RECOIL_MAX_SINGLE_MOVE_Y', 50.0)

            if abs(offset_x) > max_single_move_x:
                if self.debug_mode:
                    utils.log(f"[自动压枪] X轴单次偏移过大: {offset_x:+.2f}px，限制为 {max_single_move_x:+.2f}px")
                offset_x = max_single_move_x if offset_x > 0 else -max_single_move_x

            if offset_y > max_single_move_y:
                if self.debug_mode:
                    utils.log(f"[自动压枪] Y轴单次偏移过大: {offset_y:.2f}px，限制为 {max_single_move_y}px")
                offset_y = max_single_move_y

            # XY 双轴累积
            self.accumulated_offset_x += offset_x
            self.accumulated_offset_y += offset_y
            self.total_offset_x += offset_x
            self.total_offset_y += offset_y

            # XY 双轴发送（≥1px 才发送）
            move_x = 0
            move_y = 0

            if abs(self.accumulated_offset_x) >= 1.0:
                move_x = int(self.accumulated_offset_x)
                self.accumulated_offset_x -= move_x

            if abs(self.accumulated_offset_y) >= 1.0:
                move_y = int(self.accumulated_offset_y)
                self.accumulated_offset_y -= move_y

            # 只有有移动时才发送
            if move_x != 0 or move_y != 0:
                if self.debug_mode:
                    self.debug_counter += 1
                    if self.debug_counter % 50 == 1:
                        elapsed = current_time - self.fire_start_time
                        current_speed_x = self.total_offset_x / elapsed if elapsed > 0 else 0
                        current_speed_y = self.total_offset_y / elapsed if elapsed > 0 else 0
                        utils.log(
                            f"[自动压枪] 第{self.shot_count}次 | "
                            f"delta: {delta_time * 1000:.2f}ms | "
                            f"移动: ({move_x:+3d}, {move_y:+3d})px | "
                            f"速度: X={current_speed_x:+.1f} Y={current_speed_y:.1f} px/s"
                        )

                # ⭐ 使用适配方法
                self._send_move(move_x, move_y)

    # ==================== 手动压枪模式 ====================

    def start_manual_recoil_monitor(self) -> None:
        """启动手动压枪监控线程"""
        if self.manual_recoil_thread and self.manual_recoil_thread.is_alive():
            utils.log("⚠ 手动压枪监控已在运行")
            return

        self.manual_recoil_stop_flag = False
        self.manual_recoil_thread = threading.Thread(target=self._manual_recoil_loop, daemon=True)
        self.manual_recoil_thread.start()
        utils.log("手动压枪监控已启动")

    def stop_manual_recoil_monitor(self) -> None:
        """停止手动压枪监控线程"""
        self.manual_recoil_stop_flag = True
        if self.manual_recoil_thread:
            self.manual_recoil_thread.join(timeout=2.0)
        utils.log("手动压枪监控已停止")

    def _manual_recoil_loop(self) -> None:
        """手动压枪监控循环（支持单键或双键触发 + XY双轴）"""
        trigger_mode = get_config('MANUAL_RECOIL_TRIGGER_MODE', 'left_only')

        if trigger_mode == 'left_only':
            utils.log("手动压枪模式已启动（按住左键时自动压枪）")
        elif trigger_mode == 'both_buttons':
            utils.log("手动压枪模式已启动（同时按住左键+右键时自动压枪）")

        last_trigger_state = False
        manual_fire_start_time = 0.0
        manual_last_recoil_time = 0.0
        manual_accumulated_offset_x = 0.0
        manual_accumulated_offset_y = 0.0
        manual_total_offset_x = 0.0
        manual_total_offset_y = 0.0
        manual_shot_count = 0

        try:
            while not self.manual_recoil_stop_flag:
                left_button_state = win32api.GetKeyState(0x01) < 0
                right_button_state = win32api.GetKeyState(0x02) < 0

                if trigger_mode == 'left_only':
                    current_trigger_state = left_button_state
                elif trigger_mode == 'both_buttons':
                    current_trigger_state = left_button_state and right_button_state
                else:
                    current_trigger_state = False

                # 按下瞬间
                if current_trigger_state and not last_trigger_state:
                    self.manual_recoil_active = True
                    manual_fire_start_time = time.time()
                    manual_last_recoil_time = time.time()
                    manual_accumulated_offset_x = 0.0
                    manual_accumulated_offset_y = 0.0
                    manual_total_offset_x = 0.0
                    manual_total_offset_y = 0.0
                    manual_shot_count = 0

                    if trigger_mode == 'left_only':
                        utils.log("开始手动压枪（左键按下）")
                    else:
                        utils.log("开始手动压枪（左键+右键按下）")

                # 松开瞬间
                elif not current_trigger_state and last_trigger_state:
                    self.manual_recoil_active = False
                    fire_duration = time.time() - manual_fire_start_time
                    actual_speed_x = manual_total_offset_x / fire_duration if fire_duration > 0 else 0
                    actual_speed_y = manual_total_offset_y / fire_duration if fire_duration > 0 else 0

                    utils.log(
                        f"停止手动压枪 | 持续: {fire_duration:.2f}s | "
                        f"累积: X={manual_total_offset_x:+.1f}px Y={manual_total_offset_y:+.1f}px | "
                        f"速度: X={actual_speed_x:+.1f} Y={actual_speed_y:.1f} px/s"
                    )

                # 持续压枪
                if self.manual_recoil_active and get_config('ENABLE_RECOIL_CONTROL', True):
                    current_time = time.time()
                    delta_time = current_time - manual_last_recoil_time

                    if delta_time >= 0.001:
                        manual_last_recoil_time = current_time
                        manual_shot_count += 1

                        # 计算 XY 双轴压枪偏移
                        horizontal_speed = get_config('RECOIL_HORIZONTAL_SPEED', 0.0)
                        vertical_speed = get_config('RECOIL_VERTICAL_SPEED', 150.0)

                        offset_x = horizontal_speed * delta_time
                        offset_y = vertical_speed * delta_time

                        # 双轴限制
                        max_single_move_x = get_config('RECOIL_MAX_SINGLE_MOVE_X', 50.0)
                        max_single_move_y = get_config('RECOIL_MAX_SINGLE_MOVE_Y', 50.0)

                        if abs(offset_x) > max_single_move_x:
                            offset_x = max_single_move_x if offset_x > 0 else -max_single_move_x
                        if offset_y > max_single_move_y:
                            offset_y = max_single_move_y

                        # 累积
                        manual_accumulated_offset_x += offset_x
                        manual_accumulated_offset_y += offset_y
                        manual_total_offset_x += offset_x
                        manual_total_offset_y += offset_y

                        # 发送移动
                        move_x = 0
                        move_y = 0

                        if abs(manual_accumulated_offset_x) >= 1.0:
                            move_x = int(manual_accumulated_offset_x)
                            manual_accumulated_offset_x -= move_x

                        if abs(manual_accumulated_offset_y) >= 1.0:
                            move_y = int(manual_accumulated_offset_y)
                            manual_accumulated_offset_y -= move_y

                        if move_x != 0 or move_y != 0:
                            # ⭐ 使用适配方法
                            self._send_move(move_x, move_y)

                last_trigger_state = current_trigger_state
                time.sleep(0.001)

        except Exception as e:
            utils.log(f"手动压枪监控线程错误: {e}")

    # ==================== 压枪计算方法 ====================

    def _calculate_linear_recoil(self, delta_time: float) -> tuple:
        """线性压枪：匀速向下 + 可选横向偏移"""
        horizontal_speed = get_config('RECOIL_HORIZONTAL_SPEED', 0.0)
        vertical_speed = get_config('RECOIL_VERTICAL_SPEED', 150.0)

        offset_x = horizontal_speed * delta_time
        offset_y = vertical_speed * delta_time

        return offset_x, offset_y

    def _calculate_exponential_recoil(self, delta_time: float) -> tuple:
        """指数压枪：随子弹数增加而加速（XY双轴）"""
        base_speed_x = get_config('RECOIL_HORIZONTAL_SPEED', 0.0)
        base_speed_y = get_config('RECOIL_VERTICAL_SPEED', 100.0)
        increment = get_config('RECOIL_INCREMENT_Y', 0.5)

        current_speed_x = base_speed_x * (1.0 + increment * self.shot_count * 0.5)
        current_speed_y = base_speed_y * (1.0 + increment * self.shot_count)

        offset_x = current_speed_x * delta_time
        offset_y = current_speed_y * delta_time

        return offset_x, offset_y

    def _calculate_custom_recoil(self) -> tuple:
        """自定义压枪：使用预设的偏移序列（支持 [x, y] 或 [y] 格式）"""
        custom_pattern = get_config('RECOIL_CUSTOM_PATTERN', [])

        if not custom_pattern:
            return self._calculate_linear_recoil(0.016)

        index = self.shot_count % len(custom_pattern)
        pattern_value = custom_pattern[index]

        # 支持两种格式
        if isinstance(pattern_value, (list, tuple)) and len(pattern_value) == 2:
            return float(pattern_value[0]), float(pattern_value[1])
        else:
            horizontal_speed = get_config('RECOIL_HORIZONTAL_SPEED', 0.0)
            offset_x = horizontal_speed * 0.016
            return offset_x, float(pattern_value)

    # ==================== 状态重置 ====================

    def reset(self) -> None:
        """重置状态（目标丢失时调用）"""
        if self.is_firing:
            self.stop_firing()

        with self._lock:
            self.recent_errors.clear()
            self.total_offset_x = 0.0
            self.total_offset_y = 0.0
            self.accumulated_offset_x = 0.0
            self.accumulated_offset_y = 0.0
            self.shot_count = 0

    def is_recoil_active(self) -> bool:
        """检查压枪是否正在进行"""
        return self.is_firing or self.manual_recoil_active
