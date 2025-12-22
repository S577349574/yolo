# auto_fire_controller.py
"""自动开火与压枪控制器（智能触发：需要YOLO目标确认）"""

import threading
import time
from typing import List, Optional, Tuple

import win32api

import utils
from config_manager import get_config


class AutoFireController:
    """自动开火控制器（含压枪功能 - 需要目标确认才触发）"""

    def __init__(self, mouse_controller, key_monitor=None):
        self.mouse_controller = mouse_controller
        self.key_monitor = key_monitor  # ⭐ 保存引用

        # 状态锁
        self._lock = threading.Lock()

        # ==================== 目标状态（由外部更新）====================
        self._target_detected = False  # 是否检测到目标
        self._target_locked = False  # 是否锁定目标
        self._target_lock_frames = 0  # 锁定帧数
        self._target_distance = float('inf')  # 目标距离（像素）
        self._last_target_time = 0.0  # 最后检测到目标的时间

        # ==================== 射击状态（自动开火模式）====================
        self.is_firing = False
        self.fire_start_time = 0.0
        self.shot_count = 0

        # ==================== 准确率跟踪 ====================
        self.recent_errors: List[float] = []
        self.max_error_history = 30

        # ==================== 压枪状态（XY双轴）====================
        self.total_offset_x = 0.0
        self.total_offset_y = 0.0
        self.last_recoil_time = 0.0
        self.accumulated_offset_x = 0.0
        self.accumulated_offset_y = 0.0

        # ==================== 性能优化 ====================
        self.last_log_time = 0.0
        self.log_interval = 1.0
        self.debug_mode = get_config('AUTO_FIRE_DEBUG_MODE', False)
        self.debug_counter = 0

        # ==================== 手动压枪模式 ====================
        self.manual_recoil_active = False
        self.manual_recoil_thread: Optional[threading.Thread] = None
        self.manual_recoil_stop_flag = False

    # ==================== 目标状态更新接口（供外部调用）====================

    def update_target_status(
            self,
            detected: bool,
            locked: bool = False,
            lock_frames: int = 0,
            distance: float = float('inf')
    ) -> None:
        """
        更新目标检测状态（由主循环/YOLO调用）

        Args:
            detected: 是否检测到目标
            locked: 是否锁定目标（稳定跟踪中）
            lock_frames: 连续锁定的帧数
            distance: 准星到目标的距离（像素）
        """
        with self._lock:
            self._target_detected = detected
            self._target_locked = locked
            self._target_lock_frames = lock_frames
            self._target_distance = distance

            if detected:
                self._last_target_time = time.time()

    def get_target_status(self) -> Tuple[bool, bool, int, float]:
        """获取当前目标状态"""
        with self._lock:
            return (
                self._target_detected,
                self._target_locked,
                self._target_lock_frames,
                self._target_distance
            )

    def _should_apply_recoil(self) -> bool:
        """
        判断是否应该执行压枪（核心逻辑）

        条件组合：
        1. 压枪总开关开启
        2. 按键条件满足（左键/左键+右键）
        3. 目标条件满足（可配置）
        """
        # 检查总开关
        if not get_config('ENABLE_RECOIL_CONTROL', True):
            return False

        # 检查是否需要目标确认
        require_target = get_config('RECOIL_REQUIRE_TARGET', True)

        if require_target:
            # 严格模式：需要检测到目标
            if not self._target_detected:
                return False

            # 可选：检查目标丢失超时
            target_timeout = get_config('RECOIL_TARGET_TIMEOUT', 0.5)  # 500ms
            time_since_target = time.time() - self._last_target_time
            if time_since_target > target_timeout:
                return False

            # 可选：检查是否锁定目标（更严格）
            require_lock = get_config('RECOIL_REQUIRE_LOCK', False)
            if require_lock and not self._target_locked:
                return False

            # 可选：检查锁定帧数
            min_lock_frames = get_config('RECOIL_MIN_LOCK_FRAMES', 0)
            if self._target_lock_frames < min_lock_frames:
                return False

        return True

    # ==================== 适配新接口的辅助方法 ====================

    def _send_move(self, dx: int, dy: int) -> bool:
        """发送鼠标移动（适配新接口）"""
        if hasattr(self.mouse_controller, '_send_move'):
            return self.mouse_controller._send_move(dx, dy)
        elif hasattr(self.mouse_controller, '_send_mouse_request'):
            no_button = get_config('APP_MOUSE_NO_BUTTON', 0)
            return self.mouse_controller._send_mouse_request(dx, dy, no_button)
        else:
            utils.log("⚠ 鼠标控制器接口不兼容")
            return False

    def _send_button(self, button_flags: int) -> bool:
        """发送鼠标按钮（适配新接口）"""
        if hasattr(self.mouse_controller, '_send_button'):
            return self.mouse_controller._send_button(button_flags)
        elif hasattr(self.mouse_controller, '_send_mouse_request'):
            return self.mouse_controller._send_mouse_request(0, 0, button_flags)
        else:
            utils.log("⚠ 鼠标控制器接口不兼容")
            return False

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
                utils.log("🔫 开始自动射击")
                self.last_log_time = current_time

            left_down = get_config('APP_MOUSE_LEFT_DOWN', 1)
            self._send_button(left_down)

    def stop_firing(self) -> None:
        """停止射击（释放左键 - 自动开火模式）"""
        with self._lock:
            if not self.is_firing:
                return

            self.is_firing = False
            fire_duration = time.time() - self.fire_start_time

            left_up = get_config('APP_MOUSE_LEFT_UP', 2)
            self._send_button(left_up)

            # 计算 XY 双轴速度
            actual_speed_x = self.total_offset_x / fire_duration if fire_duration > 0 else 0
            actual_speed_y = self.total_offset_y / fire_duration if fire_duration > 0 else 0

            current_time = time.time()
            if current_time - self.last_log_time > self.log_interval:
                utils.log(
                    f"⏹ 停止射击 | 持续: {fire_duration:.2f}s | 子弹: {self.shot_count} | "
                    f"累积: X={self.total_offset_x:+.1f}px Y={self.total_offset_y:+.1f}px"
                )
                self.last_log_time = current_time

            self._reset_recoil_state()

    def apply_recoil_control(self) -> None:
        """应用压枪偏移（自动开火模式）"""
        if not self.is_firing:
            return

        # ⭐ 使用智能判断
        if not self._should_apply_recoil():
            return

        with self._lock:
            self._do_recoil_tick()

    # ==================== 手动压枪模式 ====================

    def start_manual_recoil_monitor(self) -> None:
        """启动手动压枪监控线程"""
        if self.manual_recoil_thread and self.manual_recoil_thread.is_alive():
            utils.log("⚠ 手动压枪监控已在运行")
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
        utils.log("⏹ 手动压枪监控已停止")

    def _manual_recoil_loop(self) -> None:
        """手动压枪监控循环（智能触发版本）"""
        trigger_mode = get_config('MANUAL_RECOIL_TRIGGER_MODE', 'both_buttons')
        require_target = get_config('RECOIL_REQUIRE_TARGET', True)

        mode_desc = "左键" if trigger_mode == 'left_only' else "左键+右键"
        target_desc = " + 需要目标" if require_target else ""
        utils.log(f"🎯 手动压枪模式：{mode_desc}{target_desc}")

        # ⭐ 检查是否有有效的 key_monitor
        if not self.key_monitor:
            utils.log("⚠️ 未提供 key_monitor，降级使用 WinAPI 监听")
            use_key_monitor = False
        else:
            utils.log(f"✅ 使用 {type(self.key_monitor).__name__} 进行按键监听")
            use_key_monitor = True
        last_trigger_state = False
        last_recoil_active = False  # 用于检测压枪状态变化

        manual_fire_start_time = 0.0
        manual_last_recoil_time = 0.0
        manual_accumulated_offset_x = 0.0
        manual_accumulated_offset_y = 0.0
        manual_total_offset_x = 0.0
        manual_total_offset_y = 0.0
        manual_shot_count = 0

        # 状态机
        recoil_paused_logged = False  # 防止重复日志

        try:
            while not self.manual_recoil_stop_flag:
                # ⭐ 统一按键检测接口
                if use_key_monitor:
                    # 使用 key_monitor（支持硬件/软件）
                    left_pressed = self.key_monitor.is_key_pressed('left')
                    right_pressed = self.key_monitor.is_key_pressed('right')
                else:
                    # 降级使用 WinAPI（兜底）
                    import win32api
                    left_pressed = win32api.GetKeyState(0x01) < 0
                    right_pressed = win32api.GetKeyState(0x02) < 0

                # 判断触发条件
                if trigger_mode == 'left_only':
                    button_condition = left_pressed
                elif trigger_mode == 'both_buttons':
                    button_condition = left_pressed and right_pressed
                else:
                    button_condition = False

                # ⭐ 综合判断：按键 + 目标条件
                should_recoil = button_condition and self._should_apply_recoil()

                # 状态变化检测
                if should_recoil and not last_recoil_active:
                    # 开始压枪
                    self.manual_recoil_active = True
                    manual_fire_start_time = time.time()
                    manual_last_recoil_time = time.time()
                    manual_accumulated_offset_x = 0.0
                    manual_accumulated_offset_y = 0.0
                    manual_total_offset_x = 0.0
                    manual_total_offset_y = 0.0
                    manual_shot_count = 0
                    recoil_paused_logged = False

                    if self.debug_mode:
                        utils.log("🔫 开始手动压枪")

                elif not should_recoil and last_recoil_active:
                    # 停止压枪
                    self.manual_recoil_active = False
                    fire_duration = time.time() - manual_fire_start_time

                    if fire_duration > 0.1:  # 只记录有效压枪
                        # 判断停止原因
                        if not button_condition:
                            reason = "按键释放"
                        elif not self._target_detected:
                            reason = "目标丢失"
                        else:
                            reason = "条件不满足"

                        if self.debug_mode:
                            utils.log(
                                f"⏹ 停止压枪 ({reason}) | 持续: {fire_duration:.2f}s | "
                                f"子弹: {manual_shot_count} | "
                                f"累积: X={manual_total_offset_x:+.1f}px Y={manual_total_offset_y:+.1f}px"
                            )

                    recoil_paused_logged = False

                # ⭐ 按键按下但目标丢失的情况
                elif button_condition and not should_recoil and not recoil_paused_logged:
                    if self.debug_mode:
                        utils.log("⏸ 压枪暂停：等待目标...")
                    recoil_paused_logged = True

                # 执行压枪
                if self.manual_recoil_active:
                    current_time = time.time()
                    delta_time = current_time - manual_last_recoil_time

                    if delta_time >= 0.001:
                        manual_last_recoil_time = current_time
                        manual_shot_count += 1

                        # 计算偏移
                        offset_x, offset_y = self._calculate_recoil_offset(delta_time, manual_shot_count)

                        # 限幅
                        offset_x, offset_y = self._clamp_recoil_offset(offset_x, offset_y)

                        # 累积
                        manual_accumulated_offset_x += offset_x
                        manual_accumulated_offset_y += offset_y
                        manual_total_offset_x += offset_x
                        manual_total_offset_y += offset_y

                        # 发送移动（≥1px）
                        move_x, move_y = 0, 0

                        if abs(manual_accumulated_offset_x) >= 1.0:
                            move_x = int(manual_accumulated_offset_x)
                            manual_accumulated_offset_x -= move_x

                        if abs(manual_accumulated_offset_y) >= 1.0:
                            move_y = int(manual_accumulated_offset_y)
                            manual_accumulated_offset_y -= move_y

                        if move_x != 0 or move_y != 0:
                            self._send_move(move_x, move_y)

                last_trigger_state = button_condition
                last_recoil_active = should_recoil
                time.sleep(0.001)

        except Exception as e:
            utils.log(f"❌ 手动压枪监控线程错误: {e}")
            import traceback
            traceback.print_exc()

    # ==================== 压枪计算方法（通用）====================

    def _calculate_recoil_offset(self, delta_time: float, shot_count: int) -> Tuple[float, float]:
        """计算压枪偏移（通用方法）"""
        pattern = get_config('RECOIL_PATTERN', 'linear')

        if pattern == 'linear':
            return self._calculate_linear_recoil(delta_time)
        elif pattern == 'exponential':
            return self._calculate_exponential_recoil(delta_time, shot_count)
        elif pattern == 'custom':
            return self._calculate_custom_recoil(shot_count)
        else:
            return self._calculate_linear_recoil(delta_time)

    def _calculate_linear_recoil(self, delta_time: float) -> Tuple[float, float]:
        """线性压枪"""
        horizontal_speed = get_config('RECOIL_HORIZONTAL_SPEED', 0.0)
        vertical_speed = get_config('RECOIL_VERTICAL_SPEED', 150.0)

        return horizontal_speed * delta_time, vertical_speed * delta_time

    def _calculate_exponential_recoil(self, delta_time: float, shot_count: int) -> Tuple[float, float]:
        """指数压枪"""
        base_speed_x = get_config('RECOIL_HORIZONTAL_SPEED', 0.0)
        base_speed_y = get_config('RECOIL_VERTICAL_SPEED', 100.0)
        increment = get_config('RECOIL_INCREMENT_Y', 0.5)

        current_speed_x = base_speed_x * (1.0 + increment * shot_count * 0.5)
        current_speed_y = base_speed_y * (1.0 + increment * shot_count)

        return current_speed_x * delta_time, current_speed_y * delta_time

    def _calculate_custom_recoil(self, shot_count: int) -> Tuple[float, float]:
        """自定义压枪"""
        custom_pattern = get_config('RECOIL_CUSTOM_PATTERN', [])

        if not custom_pattern:
            return self._calculate_linear_recoil(0.016)

        index = shot_count % len(custom_pattern)
        pattern_value = custom_pattern[index]

        if isinstance(pattern_value, (list, tuple)) and len(pattern_value) == 2:
            return float(pattern_value[0]), float(pattern_value[1])
        else:
            horizontal_speed = get_config('RECOIL_HORIZONTAL_SPEED', 0.0)
            return horizontal_speed * 0.016, float(pattern_value)

    def _clamp_recoil_offset(self, offset_x: float, offset_y: float) -> Tuple[float, float]:
        """限制压枪偏移范围"""
        max_x = get_config('RECOIL_MAX_SINGLE_MOVE_X', 50.0)
        max_y = get_config('RECOIL_MAX_SINGLE_MOVE_Y', 50.0)

        if abs(offset_x) > max_x:
            offset_x = max_x if offset_x > 0 else -max_x
        if offset_y > max_y:
            offset_y = max_y

        return offset_x, offset_y

    def _do_recoil_tick(self) -> None:
        """执行一次压枪计算和发送"""
        current_time = time.time()
        delta_time = current_time - self.last_recoil_time

        if delta_time < 0.001:
            return

        self.last_recoil_time = current_time
        self.shot_count += 1

        # 计算偏移
        offset_x, offset_y = self._calculate_recoil_offset(delta_time, self.shot_count)
        offset_x, offset_y = self._clamp_recoil_offset(offset_x, offset_y)

        # 累积
        self.accumulated_offset_x += offset_x
        self.accumulated_offset_y += offset_y
        self.total_offset_x += offset_x
        self.total_offset_y += offset_y

        # 发送
        move_x, move_y = 0, 0

        if abs(self.accumulated_offset_x) >= 1.0:
            move_x = int(self.accumulated_offset_x)
            self.accumulated_offset_x -= move_x

        if abs(self.accumulated_offset_y) >= 1.0:
            move_y = int(self.accumulated_offset_y)
            self.accumulated_offset_y -= move_y

        if move_x != 0 or move_y != 0:
            self._send_move(move_x, move_y)

    def _reset_recoil_state(self) -> None:
        """重置压枪状态"""
        self.total_offset_x = 0.0
        self.total_offset_y = 0.0
        self.accumulated_offset_x = 0.0
        self.accumulated_offset_y = 0.0
        self.shot_count = 0

    # ==================== 状态重置 ====================

    def reset(self) -> None:
        """重置状态（目标丢失时调用）"""
        if self.is_firing:
            self.stop_firing()

        with self._lock:
            self.recent_errors.clear()
            self._reset_recoil_state()
            # 不重置目标状态，让外部控制

    def is_recoil_active(self) -> bool:
        """检查压枪是否正在进行"""
        return self.is_firing or self.manual_recoil_active
