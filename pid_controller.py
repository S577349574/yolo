# pid_controller.py
# 双轴独立参数 PID 控制器（支持配置热重载）

import time
from collections import deque
from typing import Tuple, Optional

from config_manager import get_config, on_config_change


class PIDController:
    """
    双轴独立参数 PID 控制器

    特性：
    - X/Y 轴独立 PID 参数
    - 支持配置热重载（参数变更自动生效）
    - 积分抗饱和
    - 微分限幅
    - 死区过滤
    - dt 平滑（中值滤波）
    """

    def __init__(self):
        # ========== X 轴 PID 参数 ==========
        self.kp_x: float = get_config('PID_KP_X', 0.15)
        self.ki_x: float = get_config('PID_KI_X', 0.05)
        self.kd_x: float = get_config('PID_KD_X', 0.05)

        # ========== Y 轴 PID 参数 ==========
        self.kp_y: float = get_config('PID_KP_Y', 0.15)
        self.ki_y: float = get_config('PID_KI_Y', 0.05)
        self.kd_y: float = get_config('PID_KD_Y', 0.05)

        # ========== 限制参数 ==========
        self.max_move: int = get_config('MAX_SINGLE_MOVE_PX', 400)
        self.dead_zone: int = get_config('PRECISION_DEAD_ZONE', 5)
        self.delay_ms: int = get_config('DEFAULT_DELAY_MS_PER_STEP', 1)

        # ========== 瞄准偏移 ==========
        self.aim_y_ratio: float = get_config('AIM_Y_RATIO', 0.5)
        self.aim_x_offset: float = get_config('AIM_X_OFFSET', 0.0)

        # ========== 调试模式 ==========
        self.debug_mode: bool = get_config('DEBUG_MODE', False)

        # ========== 内部状态 ==========
        self.integral_x: float = 0.0
        self.integral_y: float = 0.0
        self.last_error_x: float = 0.0
        self.last_error_y: float = 0.0
        self.last_time: float = time.perf_counter()

        # 积分限制（抗饱和）
        self.integral_limit: float = 100.0

        # 积分衰减阈值
        self.integral_decay_threshold: float = 50.0

        # dt 平滑缓冲（中值滤波）
        self._dt_history: deque = deque(maxlen=5)

        # 输出历史（用于平滑，可选）
        self._output_history_x: deque = deque(maxlen=3)
        self._output_history_y: deque = deque(maxlen=3)

        # ⭐ 注册配置变更回调（实现热重载）
        self._register_config_callbacks()

        if self.debug_mode:
            self._log_params("初始化完成")

    def _register_config_callbacks(self) -> None:
        """注册所有 PID 相关配置的变更回调"""
        # X 轴 PID 参数
        on_config_change("PID_KP_X", lambda v: self._update_param('kp_x', v, reset_integral=True))
        on_config_change("PID_KI_X", lambda v: self._update_param('ki_x', v, reset_integral=True))
        on_config_change("PID_KD_X", lambda v: self._update_param('kd_x', v, reset_integral=False))

        # Y 轴 PID 参数
        on_config_change("PID_KP_Y", lambda v: self._update_param('kp_y', v, reset_integral=True))
        on_config_change("PID_KI_Y", lambda v: self._update_param('ki_y', v, reset_integral=True))
        on_config_change("PID_KD_Y", lambda v: self._update_param('kd_y', v, reset_integral=False))

        # 限制参数
        on_config_change("MAX_SINGLE_MOVE_PX", lambda v: self._update_param('max_move', v))
        on_config_change("PRECISION_DEAD_ZONE", lambda v: self._update_param('dead_zone', v))
        on_config_change("DEFAULT_DELAY_MS_PER_STEP", lambda v: self._update_param('delay_ms', v))

        # 瞄准偏移
        on_config_change("AIM_Y_RATIO", lambda v: self._update_param('aim_y_ratio', v))
        on_config_change("AIM_X_OFFSET", lambda v: self._update_param('aim_x_offset', v))

        # 调试模式
        on_config_change("DEBUG_MODE", lambda v: self._update_param('debug_mode', v))

    def _update_param(self, name: str, value, reset_integral: bool = False) -> None:
        """
        更新参数值

        Args:
            name: 参数名称
            value: 新值
            reset_integral: 是否重置积分项（PID 参数变更时建议重置）
        """
        old_value = getattr(self, name, None)

        # 类型转换
        if isinstance(old_value, float):
            value = float(value)
        elif isinstance(old_value, int):
            value = int(value)
        elif isinstance(old_value, bool):
            value = bool(value)

        setattr(self, name, value)

        # PID 核心参数变更时重置积分项（避免累积误差影响新参数效果）
        if reset_integral:
            self.integral_x = 0.0
            self.integral_y = 0.0
            self._output_history_x.clear()
            self._output_history_y.clear()

        if self.debug_mode:
            print(f"[PID] 🔄 参数热更新: {name} = {old_value} → {value}" +
                  (" (积分已重置)" if reset_integral else ""))

    def _log_params(self, prefix: str = "") -> None:
        """打印当前参数状态"""
        print(f"[PID] {prefix}")
        print(f"      X轴: Kp={self.kp_x:.3f}, Ki={self.ki_x:.3f}, Kd={self.kd_x:.3f}")
        print(f"      Y轴: Kp={self.kp_y:.3f}, Ki={self.ki_y:.3f}, Kd={self.kd_y:.3f}")
        print(f"      限制: max_move={self.max_move}, dead_zone={self.dead_zone}")

    def reset(self) -> None:
        """完全重置 PID 控制器状态"""
        self.integral_x = 0.0
        self.integral_y = 0.0
        self.last_error_x = 0.0
        self.last_error_y = 0.0
        self.last_time = time.perf_counter()
        self._dt_history.clear()
        self._output_history_x.clear()
        self._output_history_y.clear()

        if self.debug_mode:
            print("[PID] ✅ 控制器状态已重置")

    def soft_reset(self) -> None:
        """软重置（仅清除积分项，保留其他状态）"""
        self.integral_x = 0.0
        self.integral_y = 0.0

    def get_smoothed_dt(self, raw_dt: float) -> float:
        """
        获取平滑后的 dt（使用中值滤波）

        Args:
            raw_dt: 原始时间差

        Returns:
            平滑后的 dt
        """
        self._dt_history.append(raw_dt)

        if len(self._dt_history) >= 3:
            # 中值滤波
            sorted_dt = sorted(self._dt_history)
            return sorted_dt[len(sorted_dt) // 2]

        return raw_dt

    def compute(self, error_x: float, error_y: float) -> Tuple[int, int]:
        """
        计算 PID 输出

        Args:
            error_x: X 轴误差（目标位置 - 当前位置，正值表示目标在右边）
            error_y: Y 轴误差（正值表示目标在下方）

        Returns:
            (move_x, move_y): 鼠标移动量（像素）
        """
        # ========== 1. 计算时间差 ==========
        current_time = time.perf_counter()
        raw_dt = current_time - self.last_time
        self.last_time = current_time

        # dt 平滑
        dt = self.get_smoothed_dt(raw_dt)

        # 防止 dt 异常
        dt = max(0.0005, min(dt, 0.1))  # 限制在 0.5ms ~ 100ms

        # ========== 2. 死区检测 ==========
        if abs(error_x) < self.dead_zone and abs(error_y) < self.dead_zone:
            # 在死区内，快速衰减积分并返回零
            self.integral_x *= 0.5
            self.integral_y *= 0.5
            return 0, 0

        # ========== 3. X 轴 PID 计算 ==========
        output_x = self._compute_axis(
            error=error_x,
            integral=self.integral_x,
            last_error=self.last_error_x,
            kp=self.kp_x,
            ki=self.ki_x,
            kd=self.kd_x,
            dt=dt,
            axis='X'
        )

        # 更新 X 轴状态
        self.integral_x = self._update_integral(error_x, self.integral_x, dt)
        self.last_error_x = error_x

        # ========== 4. Y 轴 PID 计算 ==========
        output_y = self._compute_axis(
            error=error_y,
            integral=self.integral_y,
            last_error=self.last_error_y,
            kp=self.kp_y,
            ki=self.ki_y,
            kd=self.kd_y,
            dt=dt,
            axis='Y'
        )

        # 更新 Y 轴状态
        self.integral_y = self._update_integral(error_y, self.integral_y, dt)
        self.last_error_y = error_y

        # ========== 5. 输出限幅 ==========
        output_x = self._clamp(output_x, -self.max_move, self.max_move)
        output_y = self._clamp(output_y, -self.max_move, self.max_move)

        # ========== 6. 调试输出 ==========
        if self.debug_mode and (abs(error_x) > 10 or abs(error_y) > 10):
            print(
                f"[PID] err=({error_x:+.1f}, {error_y:+.1f}) → out=({output_x:+.1f}, {output_y:+.1f}) dt={dt * 1000:.1f}ms")

        return int(round(output_x)), int(round(output_y))

    def _compute_axis(self, error: float, integral: float, last_error: float,
                      kp: float, ki: float, kd: float, dt: float, axis: str) -> float:
        """
        计算单轴 PID 输出

        Args:
            error: 当前误差
            integral: 积分累积值
            last_error: 上一次误差
            kp, ki, kd: PID 参数
            dt: 时间差
            axis: 轴标识（用于调试）

        Returns:
            PID 输出值
        """
        # P - 比例项
        p_term = kp * error

        # I - 积分项
        i_term = ki * integral

        # D - 微分项（带限幅，防止噪声放大）
        if dt > 0:
            derivative = (error - last_error) / dt
        else:
            derivative = 0.0

        # 微分限幅（根据误差大小动态调整）
        if abs(error) < 30:
            d_limit = 50.0  # 小误差时限制更严格
        else:
            d_limit = 100.0

        derivative = self._clamp(derivative, -d_limit, d_limit)
        d_term = kd * derivative

        # 总输出
        output = p_term + i_term + d_term

        return output

    def _update_integral(self, error: float, current_integral: float, dt: float) -> float:
        """
        更新积分项（带抗饱和）

        Args:
            error: 当前误差
            current_integral: 当前积分值
            dt: 时间差

        Returns:
            更新后的积分值
        """
        abs_error = abs(error)

        if abs_error < self.integral_decay_threshold:
            # 小误差：正常累积积分
            new_integral = current_integral + error * dt
            # 限幅（抗饱和）
            new_integral = self._clamp(new_integral, -self.integral_limit, self.integral_limit)
        else:
            # 大误差：衰减积分（防止过冲）
            new_integral = current_integral * 0.9

        return new_integral

    def _clamp(self, value: float, min_val: float, max_val: float) -> float:
        """限幅函数"""
        return max(min_val, min(max_val, value))

    def compute_with_smoothing(self, error_x: float, error_y: float,
                               smooth_factor: float = 0.3) -> Tuple[int, int]:
        """
        计算 PID 输出（带输出平滑）

        Args:
            error_x: X 轴误差
            error_y: Y 轴误差
            smooth_factor: 平滑因子 (0-1)，越大越平滑

        Returns:
            (move_x, move_y): 平滑后的鼠标移动量
        """
        raw_x, raw_y = self.compute(error_x, error_y)

        # 加入历史
        self._output_history_x.append(raw_x)
        self._output_history_y.append(raw_y)

        if len(self._output_history_x) >= 2:
            # EMA 平滑
            smooth_x = raw_x * (1 - smooth_factor) + self._output_history_x[-2] * smooth_factor
            smooth_y = raw_y * (1 - smooth_factor) + self._output_history_y[-2] * smooth_factor
            return int(round(smooth_x)), int(round(smooth_y))

        return raw_x, raw_y

    def get_delay(self) -> float:
        """获取每步延迟（秒）"""
        return self.delay_ms / 1000.0

    def get_params(self) -> dict:
        """获取当前所有参数（用于调试/保存）"""
        return {
            'kp_x': self.kp_x,
            'ki_x': self.ki_x,
            'kd_x': self.kd_x,
            'kp_y': self.kp_y,
            'ki_y': self.ki_y,
            'kd_y': self.kd_y,
            'max_move': self.max_move,
            'dead_zone': self.dead_zone,
            'delay_ms': self.delay_ms,
            'integral_limit': self.integral_limit,
        }

    def set_params(self, params: dict) -> None:
        """批量设置参数"""
        for key, value in params.items():
            if hasattr(self, key):
                self._update_param(key, value, reset_integral=True)

    def __repr__(self) -> str:
        return (f"PIDController(kp_x={self.kp_x}, ki_x={self.ki_x}, kd_x={self.kd_x}, "
                f"kp_y={self.kp_y}, ki_y={self.ki_y}, kd_y={self.kd_y}, "
                f"max_move={self.max_move}, dead_zone={self.dead_zone})")


# ========== 便捷工厂函数 ==========

def create_pid_controller() -> PIDController:
    """创建并返回 PID 控制器实例"""
    return PIDController()


# ========== 单元测试 ==========

if __name__ == "__main__":
    print("=" * 50)
    print("PID 控制器测试")
    print("=" * 50)

    # 创建控制器
    pid = create_pid_controller()
    print(f"\n创建控制器: {pid}")
    print(f"当前参数: {pid.get_params()}")

    # 模拟误差序列
    test_errors = [
        (100, 50),  # 大误差
        (80, 40),
        (50, 25),
        (20, 10),
        (5, 3),  # 接近死区
        (2, 1),  # 在死区内
    ]

    print("\n模拟 PID 响应:")
    print("-" * 50)

    for i, (ex, ey) in enumerate(test_errors):
        time.sleep(0.016)  # 模拟 60 FPS
        move_x, move_y = pid.compute(ex, ey)
        print(f"帧 {i + 1}: 误差=({ex:+4d}, {ey:+4d}) → 移动=({move_x:+4d}, {move_y:+4d})")

    print("-" * 50)
    print("\n测试完成！")
