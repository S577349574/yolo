# auto_fire_controller.py
"""自动开火与压枪控制器（支持两种互斥模式）"""

import threading
import time
from typing import List

import win32api

import utils
from config_manager import get_config


class AutoFireController:
    """自动开火控制器（含压枪功能 - 支持手动/自动两种模式）"""

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

        # 压枪状态
        self.total_offset_y = 0.0
        self.last_recoil_time = 0.0
        self.accumulated_offset_y = 0.0

        # 性能优化
        self.last_log_time = 0.0
        self.log_interval = 1.0
        self.debug_mode = get_config('AUTO_FIRE_DEBUG_MODE', False)
        self.debug_counter = 0

        # 🆕 手动压枪模式
        self.manual_recoil_active = False
        self.manual_recoil_thread = None
        self.manual_recoil_stop_flag = False

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

    def start_firing(self) -> None:
        """开始射击（按下左键 - 自动开火模式）"""
        with self._lock:
            if self.is_firing:
                return

            self.is_firing = True
            self.fire_start_time = time.time()
            self.last_recoil_time = time.time()
            self.total_offset_y = 0.0
            self.accumulated_offset_y = 0.0
            self.shot_count = 0
            self.debug_counter = 0

            current_time = time.time()
            if current_time - self.last_log_time > self.log_interval:
                utils.log("🔥 开始自动射击")
                self.last_log_time = current_time

            left_down = get_config('APP_MOUSE_LEFT_DOWN', 1)
            self.mouse_controller._send_mouse_request(0, 0, left_down)

    def stop_firing(self) -> None:
        """停止射击（释放左键 - 自动开火模式）"""
        with self._lock:
            if not self.is_firing:
                return

            self.is_firing = False
            fire_duration = time.time() - self.fire_start_time

            left_up = get_config('APP_MOUSE_LEFT_UP', 2)
            self.mouse_controller._send_mouse_request(0, 0, left_up)

            actual_speed = self.total_offset_y / fire_duration if fire_duration > 0 else 0
            theoretical_speed = get_config('RECOIL_VERTICAL_SPEED', 150.0)

            current_time = time.time()
            if current_time - self.last_log_time > self.log_interval:
                utils.log(
                    f"🛑 停止射击 | 持续: {fire_duration:.2f}s | "
                    f"累积: {self.total_offset_y:.1f}px | 子弹: {self.shot_count} | "
                    f"速度: {actual_speed:.1f}/{theoretical_speed:.1f} px/s"
                )
                self.last_log_time = current_time

            self.total_offset_y = 0.0
            self.accumulated_offset_y = 0.0
            self.shot_count = 0

    def apply_recoil_control(self) -> None:
        """应用压枪偏移（自动开火模式 - 累积发送版本）"""
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

            if pattern == 'linear':
                offset_y = self._calculate_linear_recoil(delta_time)
            elif pattern == 'exponential':
                offset_y = self._calculate_exponential_recoil(delta_time)
            elif pattern == 'custom':
                offset_y = self._calculate_custom_recoil()
            else:
                offset_y = self._calculate_linear_recoil(delta_time)

            max_single_move = get_config('RECOIL_MAX_SINGLE_MOVE', 50.0)
            if offset_y > max_single_move:
                if self.debug_mode:
                    utils.log(f"⚠️ [自动压枪] 单次偏移过大: {offset_y:.2f}px，限制为 {max_single_move}px")
                offset_y = max_single_move

            self.accumulated_offset_y += offset_y
            self.total_offset_y += offset_y

            if abs(self.accumulated_offset_y) >= 1.0:
                move_y = int(self.accumulated_offset_y)
                self.accumulated_offset_y -= move_y

                if self.debug_mode:
                    self.debug_counter += 1
                    if self.debug_counter % 50 == 1:
                        elapsed = current_time - self.fire_start_time
                        current_speed = self.total_offset_y / elapsed if elapsed > 0 else 0
                        utils.log(
                            f"[自动压枪] 第{self.shot_count}次 | "
                            f"delta: {delta_time * 1000:.2f}ms | "
                            f"实际移动: {move_y}px | "
                            f"速度: {current_speed:.1f} px/s"
                        )

                self.mouse_controller._send_mouse_request(
                    0,
                    move_y,
                    get_config('APP_MOUSE_NO_BUTTON', 0)
                )

    # 🆕 手动压枪模式相关方法
    def start_manual_recoil_monitor(self) -> None:
        """启动手动压枪监控线程"""
        if self.manual_recoil_thread and self.manual_recoil_thread.is_alive():
            utils.log("⚠️ 手动压枪监控已在运行")
            return

        self.manual_recoil_stop_flag = False
        self.manual_recoil_thread = threading.Thread(target=self._manual_recoil_loop, daemon=True)
        self.manual_recoil_thread.start()
        utils.log("✅ 手动压枪监控已启动")

    def stop_manual_recoil_monitor(self) -> None:
        """停止手动压枪监控线程"""
        self.manual_recoil_stop_flag = True
        if self.manual_recoil_thread:
            self.manual_recoil_thread.join(timeout=2.0)
        utils.log("✅ 手动压枪监控已停止")

    def _manual_recoil_loop(self) -> None:
        """手动压枪监控循环（支持单键或双键触发）"""
        # 🆕 读取触发模式
        trigger_mode = get_config('MANUAL_RECOIL_TRIGGER_MODE', 'left_only')

        if trigger_mode == 'left_only':
            utils.log("🎯 手动压枪模式已启动（按住左键时自动压枪）")
        elif trigger_mode == 'both_buttons':
            utils.log("🎯 手动压枪模式已启动（同时按住左键+右键时自动压枪）")

        last_trigger_state = False  # 上一帧触发状态
        manual_fire_start_time = 0.0
        manual_last_recoil_time = 0.0
        manual_accumulated_offset_y = 0.0
        manual_total_offset_y = 0.0
        manual_shot_count = 0

        try:
            while not self.manual_recoil_stop_flag:
                # 🆕 根据模式检测触发条件
                left_button_state = win32api.GetKeyState(0x01) < 0
                right_button_state = win32api.GetKeyState(0x02) < 0

                if trigger_mode == 'left_only':
                    # 模式1：只需按下左键
                    current_trigger_state = left_button_state
                elif trigger_mode == 'both_buttons':
                    # 模式2：左键+右键同时按下
                    current_trigger_state = left_button_state and right_button_state
                else:
                    current_trigger_state = False

                # 按下瞬间（从未触发到触发）
                if current_trigger_state and not last_trigger_state:
                    self.manual_recoil_active = True
                    manual_fire_start_time = time.time()
                    manual_last_recoil_time = time.time()
                    manual_accumulated_offset_y = 0.0
                    manual_total_offset_y = 0.0
                    manual_shot_count = 0

                    if trigger_mode == 'left_only':
                        utils.log("🔥 开始手动压枪（左键按下）")
                    else:
                        utils.log("🔥 开始手动压枪（左键+右键按下）")

                # 松开瞬间（从触发到未触发）
                elif not current_trigger_state and last_trigger_state:
                    self.manual_recoil_active = False
                    fire_duration = time.time() - manual_fire_start_time
                    actual_speed = manual_total_offset_y / fire_duration if fire_duration > 0 else 0

                    utils.log(
                        f"🛑 停止手动压枪 | 持续: {fire_duration:.2f}s | "
                        f"累积: {manual_total_offset_y:.1f}px | "
                        f"速度: {actual_speed:.1f} px/s"
                    )

                # 持续压枪
                if self.manual_recoil_active and get_config('ENABLE_RECOIL_CONTROL', True):
                    current_time = time.time()
                    delta_time = current_time - manual_last_recoil_time

                    if delta_time >= 0.001:
                        manual_last_recoil_time = current_time
                        manual_shot_count += 1

                        # 计算压枪偏移
                        vertical_speed = get_config('RECOIL_VERTICAL_SPEED', 150.0)
                        offset_y = vertical_speed * delta_time

                        # 单次限制
                        max_single_move = get_config('RECOIL_MAX_SINGLE_MOVE', 50.0)
                        if offset_y > max_single_move:
                            offset_y = max_single_move

                        # 累积
                        manual_accumulated_offset_y += offset_y
                        manual_total_offset_y += offset_y

                        # 发送移动
                        if abs(manual_accumulated_offset_y) >= 1.0:
                            move_y = int(manual_accumulated_offset_y)
                            manual_accumulated_offset_y -= move_y

                            self.mouse_controller._send_mouse_request(
                                0,
                                move_y,
                                get_config('APP_MOUSE_NO_BUTTON', 0)
                            )

                last_trigger_state = current_trigger_state
                time.sleep(0.001)

        except Exception as e:
            utils.log(f"❌ 手动压枪监控线程错误: {e}")

    def _calculate_linear_recoil(self, delta_time: float) -> float:
        """线性压枪：匀速向下"""
        vertical_speed = get_config('RECOIL_VERTICAL_SPEED', 150.0)
        return vertical_speed * delta_time

    def _calculate_exponential_recoil(self, delta_time: float) -> float:
        """指数压枪：随子弹数增加而加速"""
        base_speed = get_config('RECOIL_VERTICAL_SPEED', 100.0)
        increment = get_config('RECOIL_INCREMENT_Y', 0.5)
        current_speed = base_speed * (1.0 + increment * self.shot_count)
        return current_speed * delta_time

    def _calculate_custom_recoil(self) -> float:
        """自定义压枪：使用预设的偏移序列"""
        custom_pattern = get_config('RECOIL_CUSTOM_PATTERN', [])

        if not custom_pattern:
            return self._calculate_linear_recoil(0.016)

        index = self.shot_count % len(custom_pattern)
        return float(custom_pattern[index])

    def reset(self) -> None:
        """重置状态（目标丢失时调用）"""
        if self.is_firing:
            self.stop_firing()

        with self._lock:
            self.recent_errors.clear()
            self.total_offset_y = 0.0
            self.accumulated_offset_y = 0.0
            self.shot_count = 0
