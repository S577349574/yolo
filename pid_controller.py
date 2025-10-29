import time
from config_manager import get_config


class PIDController:
    """简化版PID控制器"""

    def __init__(self, kp=0.95, ki=0.0, kd=0.05):
        self.kp = kp
        self.ki = ki
        self.kd = kd

        self.last_error_x = 0
        self.last_error_y = 0
        self.integral_x = 0
        self.integral_y = 0
        self.last_time = time.perf_counter()

        # 时间戳平滑（防止dt异常）
        self.dt_history = []
        self.dt_smooth_window = 3

    def reset(self):
        """重置PID状态"""
        self.last_error_x = 0
        self.last_error_y = 0
        self.integral_x = 0
        self.integral_y = 0
        self.last_time = time.perf_counter()
        self.dt_history.clear()

    def _get_stable_dt(self, raw_dt):
        """平滑时间差（防止核心切换导致的dt抖动）"""
        if raw_dt <= 0 or raw_dt > 0.5:
            raw_dt = 0.016  # 回退到60fps标准帧时间

        self.dt_history.append(raw_dt)
        if len(self.dt_history) > self.dt_smooth_window:
            self.dt_history.pop(0)

        # 返回中位数（更抗干扰）
        sorted_dt = sorted(self.dt_history)
        return sorted_dt[len(sorted_dt) // 2]

    def calculate(self, error_x, error_y):
        """计算PID输出"""
        current_time = time.perf_counter()
        raw_dt = current_time - self.last_time
        dt = self._get_stable_dt(raw_dt)
        self.last_time = current_time

        # ========== X轴 ==========
        # P项：比例控制
        p_term_x = self.kp * error_x

        # D项：微分控制（防止过冲）
        derivative_x = (error_x - self.last_error_x) / dt

        # 限制微分变化率（防止dt过小导致爆炸）
        max_derivative = 500  # px/s
        derivative_x = max(min(derivative_x, max_derivative), -max_derivative)

        d_term_x = self.kd * derivative_x

        # D项独立限幅（防止过度修正）
        d_term_limit = 2.0
        d_term_x = max(min(d_term_x, d_term_limit), -d_term_limit)

        self.last_error_x = error_x
        output_x = p_term_x + d_term_x

        # ========== Y轴（同样逻辑）==========
        p_term_y = self.kp * error_y

        derivative_y = (error_y - self.last_error_y) / dt
        derivative_y = max(min(derivative_y, max_derivative), -max_derivative)

        d_term_y = self.kd * derivative_y
        d_term_y = max(min(d_term_y, d_term_limit), -d_term_limit)

        self.last_error_y = error_y
        output_y = p_term_y + d_term_y

        # 总输出限幅（使用配置）
        max_output = get_config("MAX_SINGLE_MOVE_PX", 200)
        output_x = max(min(output_x, max_output), -max_output)
        output_y = max(min(output_y, max_output), -max_output)

        return output_x, output_y
