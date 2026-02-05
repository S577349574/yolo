# controllers/recoil_controller.py
"""压枪控制器（计算 + 手动监控）"""

import threading
import time
from typing import Tuple, Optional, Callable

import utils
from config_manager import get_config


class RecoilCalculator:
    """
    压枪计算器（纯算法，无状态）

    支持的压枪模式：
    - linear: 线性压枪
    - exponential: 指数增长压枪
    - custom: 自定义模式数组
    """

    @staticmethod
    def calculate_offset(
        delta_time: float,
        shot_count: int,
        pattern: str = 'linear'
    ) -> Tuple[float, float]:
        """
        计算压枪偏移量

        Args:
            delta_time: 时间间隔（秒）
            shot_count: 当前子弹数
            pattern: 压枪模式

        Returns:
            Tuple[float, float]: (x偏移, y偏移)
        """
        if pattern == 'linear':
            return RecoilCalculator._calculate_linear(delta_time)
        elif pattern == 'exponential':
            return RecoilCalculator._calculate_exponential(delta_time, shot_count)
        elif pattern == 'custom':
            return RecoilCalculator._calculate_custom(shot_count)
        else:
            utils.log(f"未知压枪模式: {pattern}，使用线性模式")
            return RecoilCalculator._calculate_linear(delta_time)

    @staticmethod
    def _calculate_linear(delta_time: float) -> Tuple[float, float]:
        """
        线性压枪（恒定速度）

        Args:
            delta_time: 时间间隔

        Returns:
            Tuple[float, float]: (x偏移, y偏移)
        """
        horizontal_speed = get_config('RECOIL_HORIZONTAL_SPEED', 0.0)
        vertical_speed = get_config('RECOIL_VERTICAL_SPEED', 150.0)

        offset_x = horizontal_speed * delta_time
        offset_y = vertical_speed * delta_time

        return offset_x, offset_y

    @staticmethod
    def _calculate_exponential(delta_time: float, shot_count: int) -> Tuple[float, float]:
        """
        指数压枪（随子弹数增长）

        Args:
            delta_time: 时间间隔
            shot_count: 当前子弹数

        Returns:
            Tuple[float, float]: (x偏移, y偏移)
        """
        base_speed_x = get_config('RECOIL_HORIZONTAL_SPEED', 0.0)
        base_speed_y = get_config('RECOIL_VERTICAL_SPEED', 100.0)
        increment = get_config('RECOIL_INCREMENT_Y', 0.5)

        # 速度随子弹数增长
        current_speed_x = base_speed_x * (1.0 + increment * shot_count * 0.5)
        current_speed_y = base_speed_y * (1.0 + increment * shot_count)

        offset_x = current_speed_x * delta_time
        offset_y = current_speed_y * delta_time

        return offset_x, offset_y

    @staticmethod
    def _calculate_custom(shot_count: int) -> Tuple[float, float]:
        """
        自定义压枪模式（基于预定义数组）

        Args:
            shot_count: 当前子弹数

        Returns:
            Tuple[float, float]: (x偏移, y偏移)
        """
        custom_pattern = get_config('RECOIL_CUSTOM_PATTERN', [])

        if not custom_pattern:
            utils.log("自定义压枪模式为空，使用线性模式")
            return RecoilCalculator._calculate_linear(0.016)

        # 循环使用模式数组
        index = shot_count % len(custom_pattern)
        pattern_value = custom_pattern[index]

        # 支持两种格式：[x, y] 或 单个y值
        if isinstance(pattern_value, (list, tuple)) and len(pattern_value) == 2:
            return float(pattern_value[0]), float(pattern_value[1])
        else:
            horizontal_speed = get_config('RECOIL_HORIZONTAL_SPEED', 0.0)
            return horizontal_speed * 0.016, float(pattern_value)

    @staticmethod
    def clamp_offset(offset_x: float, offset_y: float) -> Tuple[float, float]:
        """
        限制压枪偏移范围（防止单次移动过大）

        Args:
            offset_x: x偏移
            offset_y: y偏移

        Returns:
            Tuple[float, float]: 限制后的偏移
        """
        max_x = get_config('RECOIL_MAX_SINGLE_MOVE_X', 50.0)
        max_y = get_config('RECOIL_MAX_SINGLE_MOVE_Y', 50.0)

        # 限制X轴（双向）
        offset_x = max(-max_x, min(max_x, offset_x))

        # 限制Y轴（仅向下）
        offset_y = min(max_y, offset_y)

        return offset_x, offset_y


class ManualRecoilMonitor:
    """
    手动压枪监控器（独立线程）

    功能：
    - 监听按键组合（左键、左键+右键、左键+侧键等）
    - 根据目标状态决定是否压枪
    - 独立线程运行，不阻塞主循环
    """

    def __init__(
        self,
        mouse_controller,
        key_monitor,
        should_recoil_callback: Callable[[], bool]
    ):
        """
        初始化手动压枪监控器

        Args:
            mouse_controller: 鼠标控制器
            key_monitor: 按键监听器
            should_recoil_callback: 判断是否应该压枪的回调函数
        """
        self.mouse_controller = mouse_controller
        self.key_monitor = key_monitor
        self.should_recoil_callback = should_recoil_callback

        # 线程控制
        self.active = False
        self.thread: Optional[threading.Thread] = None
        self.stop_flag = False

        # 压枪状态
        self.accumulated_x = 0.0
        self.accumulated_y = 0.0
        self.total_x = 0.0
        self.total_y = 0.0
        self.shot_count = 0
        self.last_recoil_time = 0.0
        self.fire_start_time = 0.0

        # 调试模式
        self.debug_mode = get_config('AUTO_FIRE_DEBUG_MODE', False)

    def start(self) -> None:
        """启动监控线程"""
        if self.thread and self.thread.is_alive():
            utils.log("手动压枪监控已在运行")
            return

        self.stop_flag = False
        self.thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.thread.start()

        trigger_mode = get_config('MANUAL_RECOIL_TRIGGER_MODE', 'left_only')
        require_target = get_config('RECOIL_REQUIRE_TARGET', True)

        mode_desc = self._get_mode_description(trigger_mode)
        target_desc = " + 需要目标" if require_target else ""

        utils.log(f"手动压枪监控已启动 | 模式: {mode_desc}{target_desc}")

    def stop(self) -> None:
        """停止监控线程"""
        self.stop_flag = True
        if self.thread:
            self.thread.join(timeout=2.0)
        utils.log("手动压枪监控已停止")

    def _monitoring_loop(self) -> None:
        """监控循环（主逻辑）"""
        trigger_mode = get_config('MANUAL_RECOIL_TRIGGER_MODE', 'left_only')
        last_active = False
        recoil_paused_logged = False

        try:
            while not self.stop_flag:
                # 检查按键条件
                button_condition = self._check_trigger_buttons(trigger_mode)

                # 检查目标条件（通过回调）
                should_recoil = button_condition and self.should_recoil_callback()

                # ==================== 状态切换 ====================
                if should_recoil and not last_active:
                    # 开始压枪
                    self._start_recoil()
                    recoil_paused_logged = False

                elif not should_recoil and last_active:
                    # 停止压枪
                    reason = self._get_stop_reason(button_condition)
                    self._stop_recoil(reason)
                    recoil_paused_logged = False

                # ==================== 暂停提示 ====================
                elif button_condition and not should_recoil and not recoil_paused_logged:
                    if self.debug_mode:
                        utils.log("压枪暂停：等待目标...")
                    recoil_paused_logged = True

                # ==================== 执行压枪 ====================
                if self.active:
                    self._apply_recoil()

                last_active = should_recoil
                time.sleep(0.01)  # 100Hz 监控频率

        except Exception as e:
            utils.log(f"手动压枪监控线程错误: {e}")
            import traceback
            traceback.print_exc()

    def _check_trigger_buttons(self, trigger_mode: str) -> bool:
        """
        检查触发按键条件

        Args:
            trigger_mode: 触发模式

        Returns:
            bool: 按键条件是否满足
        """
        if not self.key_monitor:
            return False

        left_pressed = self.key_monitor.is_key_pressed('left')

        if trigger_mode == 'left_only':
            return left_pressed

        elif trigger_mode == 'left_right':
            right_pressed = self.key_monitor.is_key_pressed('right')
            return left_pressed and right_pressed

        elif trigger_mode == 'left_button4':
            button4_pressed = self.key_monitor.is_key_pressed('mouse4')
            return left_pressed and button4_pressed

        elif trigger_mode == 'left_button5':
            button5_pressed = self.key_monitor.is_key_pressed('mouse5')
            return left_pressed and button5_pressed

        else:
            utils.log(f"未知触发模式: {trigger_mode}，降级为仅左键")
            return left_pressed

    def _start_recoil(self) -> None:
        """开始压枪"""
        self.active = True
        self.fire_start_time = time.time()
        self.last_recoil_time = time.time()
        self.accumulated_x = 0.0
        self.accumulated_y = 0.0
        self.total_x = 0.0
        self.total_y = 0.0
        self.shot_count = 0

        if self.debug_mode:
            utils.log("开始手动压枪")

    def _stop_recoil(self, reason: str = "未知") -> None:
        """
        停止压枪

        Args:
            reason: 停止原因
        """
        self.active = False
        fire_duration = time.time() - self.fire_start_time

        # 只记录有效压枪（持续时间 > 0.1秒）
        if fire_duration > 0.1 and self.debug_mode:
            utils.log(
                f"停止压枪 ({reason}) | "
                f"持续: {fire_duration:.2f}s | "
                f"子弹: {self.shot_count} | "
                f"累积: X={self.total_x:+.1f}px Y={self.total_y:+.1f}px"
            )

    def _apply_recoil(self) -> None:
        """应用压枪（单次tick）"""
        current_time = time.time()
        delta_time = current_time - self.last_recoil_time

        # 限制最小间隔（125Hz = 8ms）
        MIN_RECOIL_INTERVAL = 0.008
        if delta_time < MIN_RECOIL_INTERVAL:
            return

        self.last_recoil_time = current_time
        self.shot_count += 1

        # 计算偏移
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
        move_x = int(self.accumulated_x) if abs(self.accumulated_x) >= 1.0 else 0
        move_y = int(self.accumulated_y) if abs(self.accumulated_y) >= 1.0 else 0

        if move_x != 0 or move_y != 0:
            self.accumulated_x -= move_x
            self.accumulated_y -= move_y
            self.mouse_controller._send_move(move_x, move_y)

    def _get_stop_reason(self, button_condition: bool) -> str:
        """
        获取停止压枪的原因

        Args:
            button_condition: 按键条件是否满足

        Returns:
            str: 停止原因描述
        """
        if not button_condition:
            return "按键释放"
        else:
            return "目标丢失"

    @staticmethod
    def _get_mode_description(trigger_mode: str) -> str:
        """获取触发模式描述"""
        mode_descriptions = {
            'left_only': '仅左键',
            'left_right': '左键+右键',
            'left_button4': '左键+侧键4',
            'left_button5': '左键+侧键5',
        }
        return mode_descriptions.get(trigger_mode, trigger_mode)
