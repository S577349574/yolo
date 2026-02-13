# controllers/auto_fire_controller.py
"""自动开火控制器（主协调器）"""

import threading
import time
from typing import Tuple

import utils
from config.config_manager import get_config
from .recoil_controller import RecoilCalculator, ManualRecoilMonitor
from .accuracy_tracker import AccuracyTracker


class AutoFireController:

    def __init__(self, mouse_controller, key_monitor=None):
        self.mouse_controller = mouse_controller
        self.key_monitor = key_monitor

        # ==================== 线程锁（最先初始化）====================
        self._lock = threading.Lock()

        # ==================== 左键状态 ====================
        self._left_button_pressed = False
        self._auto_fire_owns_button = False

        # ==================== 子模块 ====================
        self.accuracy_tracker = AccuracyTracker(
            max_history=get_config('ACCURACY_MAX_HISTORY', 30),
            base_error=get_config('ACCURACY_BASE_ERROR', 10.0)
        )

        self.manual_recoil = ManualRecoilMonitor(
            mouse_controller=mouse_controller,
            key_monitor=key_monitor,
            should_recoil_callback=self._should_apply_recoil,
            auto_fire_controller=self
        )

        # ==================== 目标状态（由外部更新）====================
        self._target_detected = False
        self._target_locked = False
        self._target_lock_frames = 0
        self._target_distance = float('inf')
        self._last_target_time = 0.0

        # ==================== 自动开火状态 ====================
        self.is_firing = False
        self.fire_start_time = 0.0
        self.shot_count = 0

        # ⭐ 新增：开火延迟
        self.fire_delay_timer = 0.0
        self.fire_delay_active = False

        # ==================== 压枪状态（自动模式）====================
        self.accumulated_x = 0.0
        self.accumulated_y = 0.0
        self.total_x = 0.0
        self.total_y = 0.0
        self.last_recoil_time = 0.0

    # ==================== 目标状态管理 ====================

    def update_target_status(
            self,
            detected: bool,
            locked: bool = False,
            lock_frames: int = 0,
            distance: float = float('inf')
    ) -> None:
        """更新目标检测状态"""
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

    # ==================== 核心判断逻辑 ====================

    def _should_apply_recoil(self) -> bool:
        """判断是否应该执行压枪"""
        enable_recoil = get_config('ENABLE_RECOIL_CONTROL', True)
        if not enable_recoil:
            return False

        require_target = get_config('RECOIL_REQUIRE_TARGET', True)
        if not require_target:
            return True

        if not self._target_detected:
            return False

        target_timeout = get_config('RECOIL_TARGET_TIMEOUT', 0.5)
        time_since_target = time.time() - self._last_target_time
        if time_since_target > target_timeout:
            return False

        require_lock = get_config('RECOIL_REQUIRE_LOCK', False)
        if require_lock and not self._target_locked:
            return False

        min_lock_frames = get_config('RECOIL_MIN_LOCK_FRAMES', 0)
        if self._target_lock_frames < min_lock_frames:
            return False

        return True

    def should_auto_fire(
            self,
            target_locked: bool,
            lock_frames: int,
            current_accuracy: float,
            error_distance: float
    ) -> bool:
        """判断是否应该自动开火"""
        enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
        if not enable_auto_fire:
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
        """开始射击（支持延迟）"""
        with self._lock:
            if self.is_firing or self.fire_delay_active:
                return

            # 获取开火延迟配置（秒）
            fire_delay = get_config('AUTO_FIRE_DELAY', 0.0)

            if fire_delay > 0:
                # 启动延迟计时
                self.fire_delay_active = True
                self.fire_delay_timer = time.time()
                return

            # 无延迟，直接开火
            self._execute_fire()

    def _execute_fire(self) -> None:
        """实际执行开火逻辑（内部方法）"""
        # 初始化射击状态
        self.is_firing = True
        self.fire_start_time = time.time()
        self.last_recoil_time = time.time()
        self.accumulated_x = 0.0
        self.accumulated_y = 0.0
        self.total_x = 0.0
        self.total_y = 0.0
        self.shot_count = 0

        # 检查是否需要发送左键按下
        if self._left_button_pressed:
            self._auto_fire_owns_button = False
        else:
            left_down = get_config('APP_MOUSE_LEFT_DOWN', 1)
            try:
                result = self.mouse_controller._send_button(left_down)
                if result is None or result is True:
                    self._left_button_pressed = True
                    self._auto_fire_owns_button = True
                else:
                    self.is_firing = False
                    return
            except Exception as e:
                utils.log(f"发送左键按下异常: {e}")
                self.is_firing = False
                return

    def update_fire_delay(self) -> None:
        """
        更新开火延迟状态（需要在主循环中调用）
        """
        if not self.fire_delay_active:
            return

        with self._lock:
            fire_delay = get_config('AUTO_FIRE_DELAY', 0.0)
            elapsed = time.time() - self.fire_delay_timer

            if elapsed >= fire_delay:
                # 延迟结束，执行开火
                self.fire_delay_active = False
                self._execute_fire()

    def stop_firing(self) -> None:
        """停止射击（释放左键）"""
        with self._lock:
            # 如果还在延迟中，取消延迟
            if self.fire_delay_active:
                self.fire_delay_active = False
                return

            if not self.is_firing:
                return

            # 只有自动开火拥有控制权时才释放左键
            if self._auto_fire_owns_button:
                left_up = get_config('APP_MOUSE_LEFT_UP', 2)
                try:
                    result = self.mouse_controller._send_button(left_up)
                    if result is None or result is True:
                        self._left_button_pressed = False
                        self._auto_fire_owns_button = False
                except Exception as e:
                    utils.log(f"发送左键释放异常: {e}")

            # 清理状态
            self.is_firing = False

    def sync_left_button_state(self, pressed: bool) -> None:
        """同步左键物理状态"""
        with self._lock:
            old_state = self._left_button_pressed
            self._left_button_pressed = pressed

            if not pressed and old_state and self._auto_fire_owns_button:
                if self.is_firing:
                    self.is_firing = False
                self._auto_fire_owns_button = False

    def apply_recoil_control(self) -> None:
        """应用压枪偏移（自动开火模式）"""
        if not self.is_firing:
            return

        if not self._should_apply_recoil():
            return

        with self._lock:
            current_time = time.time()
            delta_time = current_time - self.last_recoil_time

            MIN_RECOIL_INTERVAL = 0.008
            if delta_time < MIN_RECOIL_INTERVAL:
                return

            self.last_recoil_time = current_time
            self.shot_count += 1

            pattern = get_config('RECOIL_PATTERN', 'linear')
            offset_x, offset_y = RecoilCalculator.calculate_offset(
                delta_time, self.shot_count, pattern
            )
            offset_x, offset_y = RecoilCalculator.clamp_offset(offset_x, offset_y)

            self.accumulated_x += offset_x
            self.accumulated_y += offset_y
            self.total_x += offset_x
            self.total_y += offset_y

            move_x = 0
            move_y = 0

            if abs(self.accumulated_x) >= 1.0:
                move_x = int(self.accumulated_x)
                self.accumulated_x -= move_x

            if abs(self.accumulated_y) >= 1.0:
                move_y = int(self.accumulated_y)
                self.accumulated_y -= move_y

            if move_x != 0 or move_y != 0:
                self._send_move(move_x, move_y)

    # ==================== 手动压枪模式 ====================

    def start_manual_recoil_monitor(self) -> None:
        """启动手动压枪监控线程"""
        self.manual_recoil.start()

    def stop_manual_recoil_monitor(self) -> None:
        """停止手动压枪监控线程"""
        self.manual_recoil.stop()

    def is_recoil_active(self) -> bool:
        """检查压枪是否正在进行"""
        return self.is_firing or self.manual_recoil.active

    # ==================== 准确率跟踪 ====================

    def update_accuracy(self, error_distance: float) -> float:
        """更新准确率"""
        return self.accuracy_tracker.update(error_distance)

    def get_accuracy_statistics(self) -> dict:
        """获取准确率统计信息"""
        return self.accuracy_tracker.get_statistics()

    # ==================== 鼠标操作封装 ====================

    def _send_move(self, dx: int, dy: int) -> bool:
        """发送鼠标移动"""
        result = self.mouse_controller._send_move(dx, dy)

        if result:
            current_x, current_y = self.mouse_controller.get_crosshair_position()
            new_x = current_x + dx
            new_y = current_y + dy

            screen_w = self.mouse_controller.screen_width
            screen_h = self.mouse_controller.screen_height
            new_x = max(0, min(screen_w - 1, new_x))
            new_y = max(0, min(screen_h - 1, new_y))

            self.mouse_controller.update_crosshair_position(new_x, new_y)

        return result

    def _send_button(self, button_flags: int) -> bool:
        """发送鼠标按钮"""
        return self.mouse_controller._send_button(button_flags)

    # ==================== 状态重置 ====================

    def reset(self) -> None:
        """重置状态"""
        if self.is_firing:
            self.stop_firing()

        with self._lock:
            self.accuracy_tracker.reset()
            self.accumulated_x = 0.0
            self.accumulated_y = 0.0
            self.total_x = 0.0
            self.total_y = 0.0
            self.shot_count = 0
            self._auto_fire_owns_button = False
            self.fire_delay_active = False

    # ==================== 兼容性接口 ====================

    @property
    def recent_errors(self):
        """兼容性接口：获取最近误差列表"""
        return self.accuracy_tracker.recent_errors

    @property
    def manual_recoil_active(self):
        """兼容性接口：获取手动压枪状态"""
        return self.manual_recoil.active
