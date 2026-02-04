# controllers/auto_fire_controller.py
"""自动开火控制器（主协调器）"""

import threading
import time
from typing import Tuple, Optional

import utils
from config_manager import get_config
from .recoil_controller import RecoilCalculator, ManualRecoilMonitor
from .accuracy_tracker import AccuracyTracker


class AutoFireController:
    """
    自动开火控制器（主协调器）

    职责：
    1. 管理自动开火逻辑
    2. 协调压枪控制器
    3. 管理目标状态
    4. 提供统一接口
    """

    def __init__(self, mouse_controller, key_monitor=None):
        """
        初始化自动开火控制器

        Args:
            mouse_controller: 鼠标控制器
            key_monitor: 按键监听器（可选）
        """
        self.mouse_controller = mouse_controller
        self.key_monitor = key_monitor

        # ==================== 子模块 ====================
        self.accuracy_tracker = AccuracyTracker(
            max_history=get_config('ACCURACY_MAX_HISTORY', 30),
            base_error=get_config('ACCURACY_BASE_ERROR', 10.0)
        )

        self.manual_recoil = ManualRecoilMonitor(
            mouse_controller=mouse_controller,
            key_monitor=key_monitor,
            should_recoil_callback=self._should_apply_recoil
        )

        # ==================== 目标状态（由外部更新）====================
        self._lock = threading.Lock()
        self._target_detected = False
        self._target_locked = False
        self._target_lock_frames = 0
        self._target_distance = float('inf')
        self._last_target_time = 0.0

        # ==================== 自动开火状态 ====================
        self.is_firing = False
        self.fire_start_time = 0.0
        self.shot_count = 0

        # ==================== 压枪状态（自动模式）====================
        self.accumulated_x = 0.0
        self.accumulated_y = 0.0
        self.total_x = 0.0
        self.total_y = 0.0
        self.last_recoil_time = 0.0

        utils.log_debug("AutoFireController 初始化完成")

    # ==================== 目标状态管理 ====================

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
        """
        获取当前目标状态

        Returns:
            Tuple[bool, bool, int, float]: (检测到, 锁定, 锁定帧数, 距离)
        """
        with self._lock:
            return (
                self._target_detected,
                self._target_locked,
                self._target_lock_frames,
                self._target_distance
            )

    # ==================== 核心判断逻辑 ====================

    def _should_apply_recoil(self) -> bool:
        """
        判断是否应该执行压枪（核心逻辑）

        条件组合：
        1. 压枪总开关开启
        2. 目标条件满足（可配置）

        Returns:
            bool: 是否应该压枪
        """
        # 检查总开关
        enable_recoil = get_config('ENABLE_RECOIL_CONTROL', True)
        if not enable_recoil:
            return False

        # 检查是否需要目标确认
        require_target = get_config('RECOIL_REQUIRE_TARGET', True)

        if not require_target:
            return True

        # 需要目标确认
        if not self._target_detected:
            return False

        # 检查目标丢失超时
        target_timeout = get_config('RECOIL_TARGET_TIMEOUT', 0.5)
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

    def should_auto_fire(
        self,
        target_locked: bool,
        lock_frames: int,
        current_accuracy: float,
        error_distance: float
    ) -> bool:
        """
        判断是否应该自动开火

        Args:
            target_locked: 目标是否锁定
            lock_frames: 锁定帧数
            current_accuracy: 当前准确率
            error_distance: 误差距离

        Returns:
            bool: 是否应该开火
        """
        # 检查总开关
        enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
        if not enable_auto_fire:
            return False

        # 检查目标锁定
        if not target_locked:
            return False

        # 检查锁定帧数
        min_lock_frames = get_config('AUTO_FIRE_MIN_LOCK_FRAMES', 3)
        if lock_frames < min_lock_frames:
            return False

        # 检查准确率
        accuracy_threshold = get_config('AUTO_FIRE_ACCURACY_THRESHOLD', 0.75)
        if current_accuracy < accuracy_threshold:
            return False

        # 检查距离
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

            utils.log_debug("开始射击")

            self.is_firing = True
            self.fire_start_time = time.time()
            self.last_recoil_time = time.time()
            self.accumulated_x = 0.0
            self.accumulated_y = 0.0
            self.total_x = 0.0
            self.total_y = 0.0
            self.shot_count = 0

            # 发送左键按下
            left_down = get_config('APP_MOUSE_LEFT_DOWN', 1)
            try:
                self.mouse_controller._send_button(left_down)
            except Exception as e:
                utils.log_debug(f"发送左键按下失败: {e}")

    def stop_firing(self) -> None:
        """停止射击（释放左键 - 自动开火模式）"""
        with self._lock:
            if not self.is_firing:
                return

            self.is_firing = False
            fire_duration = time.time() - self.fire_start_time

            # 发送左键释放
            left_up = get_config('APP_MOUSE_LEFT_UP', 2)
            try:
                self.mouse_controller._send_button(left_up)
            except Exception as e:
                utils.log_debug(f"发送左键释放失败: {e}")

            # 输出射击统计
            utils.log_debug(
                f"⏹ 停止射击 | 时长: {fire_duration:.2f}s | "
                f"子弹: {self.shot_count} | "
                f"偏移: X={self.total_x:+.1f} Y={self.total_y:+.1f}"
            )

    def apply_recoil_control(self) -> None:
        """应用压枪偏移（自动开火模式）"""
        if not self.is_firing:
            return

        # 使用智能判断
        if not self._should_apply_recoil():
            return

        with self._lock:
            current_time = time.time()
            delta_time = current_time - self.last_recoil_time

            # 限制最小间隔（125Hz = 8ms）
            MIN_RECOIL_INTERVAL = 0.008
            if delta_time < MIN_RECOIL_INTERVAL:
                return

            self.last_recoil_time = current_time
            self.shot_count += 1

            # 使用 RecoilCalculator 计算偏移
            pattern = get_config('RECOIL_PATTERN', 'linear')
            offset_x, offset_y = RecoilCalculator.calculate_offset(
                delta_time, self.shot_count, pattern
            )
            offset_x, offset_y = RecoilCalculator.clamp_offset(offset_x, offset_y)

            # 累积偏移
            self.accumulated_x += offset_x
            self.accumulated_y += offset_y
            self.total_x += offset_x
            self.total_y += offset_y

            # 发送移动（只有累积超过1像素才发送）
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
        utils.log_debug("启动手动压枪监控")
        self.manual_recoil.start()

    def stop_manual_recoil_monitor(self) -> None:
        """停止手动压枪监控线程"""
        utils.log_debug("停止手动压枪监控")
        self.manual_recoil.stop()

    def is_recoil_active(self) -> bool:
        """
        检查压枪是否正在进行

        Returns:
            bool: 自动模式或手动模式是否激活
        """
        return self.is_firing or self.manual_recoil.active

    # ==================== 准确率跟踪 ====================

    def update_accuracy(self, error_distance: float) -> float:
        """
        更新准确率（基于误差距离）

        Args:
            error_distance: 误差距离（像素）

        Returns:
            float: 当前准确率 (0.0 ~ 1.0)
        """
        return self.accuracy_tracker.update(error_distance)

    def get_accuracy_statistics(self) -> dict:
        """
        获取准确率统计信息

        Returns:
            dict: 包含准确率、平均误差等信息
        """
        return self.accuracy_tracker.get_statistics()

    # ==================== 鼠标操作封装 ====================

    def _send_move(self, dx: int, dy: int) -> bool:
        """
        发送鼠标移动（带边界检查）

        Args:
            dx: X轴偏移
            dy: Y轴偏移

        Returns:
            bool: 是否发送成功
        """
        result = self.mouse_controller._send_move(dx, dy)

        if result:
            # 更新准星位置
            current_x, current_y = self.mouse_controller.get_crosshair_position()
            new_x = current_x + dx
            new_y = current_y + dy

            # 边界检查（防止超出屏幕）
            screen_w = self.mouse_controller.screen_width
            screen_h = self.mouse_controller.screen_height
            new_x = max(0, min(screen_w - 1, new_x))
            new_y = max(0, min(screen_h - 1, new_y))

            self.mouse_controller.update_crosshair_position(new_x, new_y)

        return result

    def _send_button(self, button_flags: int) -> bool:
        """
        发送鼠标按钮（简化版）

        Args:
            button_flags: 按钮标志

        Returns:
            bool: 是否发送成功
        """
        return self.mouse_controller._send_button(button_flags)

    # ==================== 状态重置 ====================

    def reset(self) -> None:
        """重置状态（目标丢失时调用）"""
        if self.is_firing:
            self.stop_firing()

        with self._lock:
            self.accuracy_tracker.reset()
            self.accumulated_x = 0.0
            self.accumulated_y = 0.0
            self.total_x = 0.0
            self.total_y = 0.0
            self.shot_count = 0

        utils.log_debug("控制器状态已重置")

    # ==================== 兼容性接口（保持向后兼容）====================

    @property
    def recent_errors(self):
        """兼容性接口：获取最近误差列表"""
        return self.accuracy_tracker.recent_errors

    @property
    def manual_recoil_active(self):
        """兼容性接口：获取手动压枪状态"""
        return self.manual_recoil.active
