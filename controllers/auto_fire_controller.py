# controllers/auto_fire_controller.py
"""自动开火控制器（主协调器 - 调试增强版）"""

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
            should_recoil_callback=self._should_apply_recoil  # 传递回调
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

        # ==================== 性能优化 ====================
        self.last_log_time = 0.0
        self.log_interval = 1.0
        self.debug_mode = get_config('AUTO_FIRE_DEBUG_MODE', False)

        # ==================== 调试统计 ====================
        self.debug_stats = {
            'start_firing_calls': 0,
            'stop_firing_calls': 0,
            'button_send_success': 0,
            'button_send_fail': 0,
            'recoil_apply_calls': 0,
            'recoil_skip_no_firing': 0,
            'recoil_skip_no_target': 0,
            'recoil_actual_moves': 0,
        }

        utils.log("✅ AutoFireController 初始化完成")
        utils.log(f"   - 鼠标控制器: {type(mouse_controller).__name__}")
        utils.log(f"   - 按键监听器: {type(key_monitor).__name__ if key_monitor else 'None'}")
        utils.log(f"   - 调试模式: {self.debug_mode}")

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
            old_detected = self._target_detected
            old_locked = self._target_locked

            self._target_detected = detected
            self._target_locked = locked
            self._target_lock_frames = lock_frames
            self._target_distance = distance

            if detected:
                self._last_target_time = time.time()

            # 🔍 调试：状态变化时输出
            if self.debug_mode and (old_detected != detected or old_locked != locked):
                utils.log(
                    f"🎯 [目标状态变化] "
                    f"检测: {old_detected}→{detected} | "
                    f"锁定: {old_locked}→{locked} | "
                    f"帧数: {lock_frames} | "
                    f"距离: {distance:.1f}px"
                )

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
            if self.debug_mode:
                utils.log("🔍 [压枪判断] 总开关关闭")
            return False

        # 检查是否需要目标确认
        require_target = get_config('RECOIL_REQUIRE_TARGET', True)

        if not require_target:
            # 不需要目标确认，直接允许压枪
            if self.debug_mode:
                utils.log("🔍 [压枪判断] 不需要目标确认，允许压枪")
            return True

        # 需要目标确认
        if not self._target_detected:
            if self.debug_mode:
                utils.log("🔍 [压枪判断] 未检测到目标")
            return False

        # 检查目标丢失超时
        target_timeout = get_config('RECOIL_TARGET_TIMEOUT', 0.5)
        time_since_target = time.time() - self._last_target_time
        if time_since_target > target_timeout:
            if self.debug_mode:
                utils.log(f"🔍 [压枪判断] 目标超时 ({time_since_target:.2f}s > {target_timeout}s)")
            return False

        # 可选：检查是否锁定目标（更严格）
        require_lock = get_config('RECOIL_REQUIRE_LOCK', False)
        if require_lock and not self._target_locked:
            if self.debug_mode:
                utils.log("🔍 [压枪判断] 需要锁定但未锁定")
            return False

        # 可选：检查锁定帧数
        min_lock_frames = get_config('RECOIL_MIN_LOCK_FRAMES', 0)
        if self._target_lock_frames < min_lock_frames:
            if self.debug_mode:
                utils.log(f"🔍 [压枪判断] 锁定帧数不足 ({self._target_lock_frames} < {min_lock_frames})")
            return False

        if self.debug_mode:
            utils.log("🔍 [压枪判断] ✅ 所有条件满足，允许压枪")
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
        # 🔍 调试：记录判断过程
        debug_info = []

        # 检查总开关
        enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
        debug_info.append(f"总开关: {enable_auto_fire}")
        if not enable_auto_fire:
            if self.debug_mode:
                utils.log(f"🔍 [自动开火判断] {' | '.join(debug_info)} → ❌ 总开关关闭")
            return False

        # 检查目标锁定
        debug_info.append(f"锁定: {target_locked}")
        if not target_locked:
            if self.debug_mode:
                utils.log(f"🔍 [自动开火判断] {' | '.join(debug_info)} → ❌ 目标未锁定")
            return False

        # 检查锁定帧数
        min_lock_frames = get_config('AUTO_FIRE_MIN_LOCK_FRAMES', 3)
        debug_info.append(f"帧数: {lock_frames}/{min_lock_frames}")
        if lock_frames < min_lock_frames:
            if self.debug_mode:
                utils.log(f"🔍 [自动开火判断] {' | '.join(debug_info)} → ❌ 锁定帧数不足")
            return False

        # 检查准确率
        accuracy_threshold = get_config('AUTO_FIRE_ACCURACY_THRESHOLD', 0.75)
        debug_info.append(f"准确率: {current_accuracy:.2%}/{accuracy_threshold:.2%}")
        if current_accuracy < accuracy_threshold:
            if self.debug_mode:
                utils.log(f"🔍 [自动开火判断] {' | '.join(debug_info)} → ❌ 准确率不足")
            return False

        # 检查距离
        distance_threshold = get_config('AUTO_FIRE_DISTANCE_THRESHOLD', 20.0)
        debug_info.append(f"距离: {error_distance:.1f}/{distance_threshold:.1f}px")
        if error_distance > distance_threshold:
            if self.debug_mode:
                utils.log(f"🔍 [自动开火判断] {' | '.join(debug_info)} → ❌ 距离过远")
            return False

        if self.debug_mode:
            utils.log(f"🔍 [自动开火判断] {' | '.join(debug_info)} → ✅ 所有条件满足")
        return True

    # ==================== 自动开火模式 ====================

    def start_firing(self) -> None:
        """开始射击（按下左键 - 自动开火模式）"""
        self.debug_stats['start_firing_calls'] += 1

        with self._lock:
            if self.is_firing:
                utils.log("⚠️ [开火] 已经在射击中，忽略重复调用")
                return

            utils.log("=" * 60)
            utils.log("🔫 [开火] 准备开始射击...")

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
            utils.log(f"🔫 [开火] 发送左键按下信号: {left_down}")

            try:
                result = self.mouse_controller._send_button(left_down)

                if result:
                    self.debug_stats['button_send_success'] += 1
                    utils.log("✅ [开火] 左键按下信号发送成功")
                else:
                    self.debug_stats['button_send_fail'] += 1
                    utils.log("❌ [开火] 左键按下信号发送失败")

                # 🔍 验证鼠标控制器状态
                utils.log(f"🔍 [开火] 鼠标控制器类型: {type(self.mouse_controller).__name__}")
                utils.log(f"🔍 [开火] 鼠标控制器方法: {hasattr(self.mouse_controller, '_send_button')}")

            except Exception as e:
                self.debug_stats['button_send_fail'] += 1
                utils.log(f"❌ [开火] 发送左键按下时出错: {e}")
                import traceback
                traceback.print_exc()

            utils.log(f"🔫 [开火] 射击状态: is_firing={self.is_firing}")
            utils.log("=" * 60)

    def stop_firing(self) -> None:
        """停止射击（释放左键 - 自动开火模式）"""
        self.debug_stats['stop_firing_calls'] += 1

        with self._lock:
            if not self.is_firing:
                utils.log("⚠️ [停火] 当前未在射击，忽略停火调用")
                return

            utils.log("=" * 60)
            utils.log("⏹ [停火] 准备停止射击...")

            self.is_firing = False
            fire_duration = time.time() - self.fire_start_time

            # 发送左键释放
            left_up = get_config('APP_MOUSE_LEFT_UP', 2)
            utils.log(f"⏹ [停火] 发送左键释放信号: {left_up}")

            try:
                result = self.mouse_controller._send_button(left_up)

                if result:
                    self.debug_stats['button_send_success'] += 1
                    utils.log("✅ [停火] 左键释放信号发送成功")
                else:
                    self.debug_stats['button_send_fail'] += 1
                    utils.log("❌ [停火] 左键释放信号发送失败")

            except Exception as e:
                self.debug_stats['button_send_fail'] += 1
                utils.log(f"❌ [停火] 发送左键释放时出错: {e}")
                import traceback
                traceback.print_exc()

            # 计算速度
            actual_speed_x = self.total_x / fire_duration if fire_duration > 0 else 0
            actual_speed_y = self.total_y / fire_duration if fire_duration > 0 else 0

            utils.log(
                f"⏹ [停火] 射击统计:\n"
                f"   - 持续时间: {fire_duration:.2f}s\n"
                f"   - 子弹数: {self.shot_count}\n"
                f"   - 累积偏移: X={self.total_x:+.1f}px Y={self.total_y:+.1f}px\n"
                f"   - 平均速度: X={actual_speed_x:+.1f}px/s Y={actual_speed_y:.1f}px/s"
            )
            utils.log("=" * 60)

    def apply_recoil_control(self) -> None:
        """应用压枪偏移（自动开火模式）"""
        self.debug_stats['recoil_apply_calls'] += 1

        if not self.is_firing:
            self.debug_stats['recoil_skip_no_firing'] += 1
            if self.debug_mode and self.debug_stats['recoil_apply_calls'] % 100 == 0:
                utils.log(f"🔍 [压枪] 未在射击，跳过 (调用次数: {self.debug_stats['recoil_apply_calls']})")
            return

        # 使用智能判断
        if not self._should_apply_recoil():
            self.debug_stats['recoil_skip_no_target'] += 1
            if self.debug_mode and self.debug_stats['recoil_skip_no_target'] % 50 == 0:
                utils.log(f"🔍 [压枪] 目标条件不满足，跳过 (跳过次数: {self.debug_stats['recoil_skip_no_target']})")
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
                self.debug_stats['recoil_actual_moves'] += 1
                self._send_move(move_x, move_y)

                if self.debug_mode and self.shot_count % 10 == 0:
                    utils.log(
                        f"🔍 [压枪] 第{self.shot_count}发 | "
                        f"移动: ({move_x:+d}, {move_y:+d}) | "
                        f"累积: X={self.total_x:+.1f} Y={self.total_y:+.1f}"
                    )

    # ==================== 手动压枪模式 ====================

    def start_manual_recoil_monitor(self) -> None:
        """启动手动压枪监控线程"""
        utils.log("🎯 [手动压枪] 启动监控线程...")
        self.manual_recoil.start()

    def stop_manual_recoil_monitor(self) -> None:
        """停止手动压枪监控线程"""
        utils.log("🎯 [手动压枪] 停止监控线程...")
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
        utils.log("🔄 [重置] 重置控制器状态...")

        if self.is_firing:
            self.stop_firing()

        with self._lock:
            self.accuracy_tracker.reset()
            self.accumulated_x = 0.0
            self.accumulated_y = 0.0
            self.total_x = 0.0
            self.total_y = 0.0
            self.shot_count = 0
            # 不重置目标状态，让外部控制

        utils.log("✅ [重置] 状态重置完成")

    # ==================== 调试统计 ====================

    def print_debug_stats(self) -> None:
        """打印调试统计信息"""
        utils.log("=" * 60)
        utils.log("📊 [调试统计]")
        utils.log(f"   开火调用次数: {self.debug_stats['start_firing_calls']}")
        utils.log(f"   停火调用次数: {self.debug_stats['stop_firing_calls']}")
        utils.log(f"   按钮发送成功: {self.debug_stats['button_send_success']}")
        utils.log(f"   按钮发送失败: {self.debug_stats['button_send_fail']}")
        utils.log(f"   压枪调用次数: {self.debug_stats['recoil_apply_calls']}")
        utils.log(f"   压枪跳过(未射击): {self.debug_stats['recoil_skip_no_firing']}")
        utils.log(f"   压枪跳过(无目标): {self.debug_stats['recoil_skip_no_target']}")
        utils.log(f"   实际移动次数: {self.debug_stats['recoil_actual_moves']}")
        utils.log(f"   当前射击状态: {self.is_firing}")
        utils.log(f"   目标检测状态: {self._target_detected}")
        utils.log(f"   目标锁定状态: {self._target_locked}")
        utils.log("=" * 60)

    def reset_debug_stats(self) -> None:
        """重置调试统计"""
        for key in self.debug_stats:
            self.debug_stats[key] = 0
        utils.log("🔄 [调试] 统计信息已重置")

    # ==================== 兼容性接口（保持向后兼容）====================

    @property
    def recent_errors(self):
        """兼容性接口：获取最近误差列表"""
        return self.accuracy_tracker.recent_errors

    @property
    def manual_recoil_active(self):
        """兼容性接口：获取手动压枪状态"""
        return self.manual_recoil.active
