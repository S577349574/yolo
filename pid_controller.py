import time
from collections import deque
from config_manager import get_config
import utils


class PIDController:
    """双轴独立参数PID控制器"""

    def __init__(self,
                 kp_x=0.85, ki_x=0.0, kd_x=0.05,
                 kp_y=0.95, ki_y=0.0, kd_y=0.06):
        """
        初始化双轴PID控制器

        Args:
            kp_x, ki_x, kd_x: X轴PID参数（水平跟踪）
            kp_y, ki_y, kd_y: Y轴PID参数（垂直跟踪，通常需要更激进）
        """
        # X轴参数（水平方向：纯目标跟踪）
        self.kp_x = kp_x
        self.ki_x = ki_x
        self.kd_x = kd_x

        # Y轴参数（垂直方向：可能需要更强响应）
        self.kp_y = kp_y
        self.ki_y = ki_y
        self.kd_y = kd_y

        # 状态变量
        self.integral_x = 0.0
        self.integral_y = 0.0
        self.last_time = time.perf_counter()

        self.dt_history = deque(maxlen=5)
        self.first_call = True

        self.error_history_x = deque(maxlen=3)
        self.error_history_y = deque(maxlen=3)

        # 预计算常量
        self._max_derivative = 1500
        self._derivative_deadzone = 50
        self._max_output = get_config("MAX_SINGLE_MOVE_PX", 300)

        # 积分限幅（防止积分饱和）
        self._max_integral = get_config("PID_MAX_INTEGRAL", 100)

        # D项限幅规则表（可分轴配置）
        self._d_limit_rules_x = [
            (30, 1.5, 15.0),
            (15, 1.2, 8.0),
            (0, 0.8, 3.0)
        ]
        self._d_limit_rules_y = [
            (30, 1.8, 18.0),  # Y轴允许更大的D项
            (15, 1.4, 10.0),
            (0, 1.0, 4.0)
        ]

        # 条件编译日志
        self.frame_count = 0
        if get_config('ENABLE_LOGGING', False):
            self._maybe_log = self._log_debug
        else:
            self._maybe_log = lambda *args: None

    def reset(self):
        """重置PID状态"""
        self.integral_x = 0.0
        self.integral_y = 0.0
        self.last_time = time.perf_counter()
        self.dt_history.clear()
        self.first_call = True
        self.error_history_x.clear()
        self.error_history_y.clear()
        self.frame_count = 0

    def set_params(self, axis='both', kp=None, ki=None, kd=None):
        """
        动态调整PID参数

        Args:
            axis: 'x', 'y', 或 'both'
            kp, ki, kd: 要设置的参数值（None表示不修改）
        """
        if axis in ('x', 'both'):
            if kp is not None: self.kp_x = kp
            if ki is not None: self.ki_x = ki
            if kd is not None: self.kd_x = kd

        if axis in ('y', 'both'):
            if kp is not None: self.kp_y = kp
            if ki is not None: self.ki_y = ki
            if kd is not None: self.kd_y = kd

    def _get_stable_dt(self, raw_dt):
        """平滑时间差"""
        if raw_dt <= 0 or raw_dt > 0.5:
            raw_dt = 0.016

        self.dt_history.append(raw_dt)
        sorted_dt = sorted(self.dt_history)
        return sorted_dt[len(sorted_dt) // 2]

    def _calculate_d_limit(self, error, p_magnitude, rules):
        """快速计算D项限幅"""
        abs_error = abs(error)
        for threshold, factor, max_val in rules:
            if abs_error > threshold:
                return min(p_magnitude * factor, max_val)
        return 3.0

    def _calculate_axis_output(self, error, error_history, integral,
                               kp, ki, kd, d_limit_rules, dt):
        """
        单轴PID计算

        Returns:
            (output, p_term, i_term, d_term, new_integral)
        """
        # P项
        p_term = kp * error

        # I项
        new_integral = integral
        if ki > 0:
            new_integral = integral + error * dt
            # 积分限幅
            new_integral = max(-self._max_integral, min(self._max_integral, new_integral))
            # 积分分离：误差过大时不累积
            if abs(error) > 50:
                new_integral = integral  # 保持不变
            i_term = ki * new_integral
        else:
            i_term = 0.0

        # D项
        if self.first_call or len(error_history) < 2:
            d_term = 0.0
        else:
            first_error = error_history[0]
            last_error = error_history[-1]
            time_span = dt * (len(error_history) - 1)

            if time_span > 0:
                derivative = (last_error - first_error) / time_span
                derivative = max(min(derivative, self._max_derivative), -self._max_derivative)

                if abs(derivative) < self._derivative_deadzone:
                    d_term = 0.0
                else:
                    d_term_raw = kd * derivative
                    d_limit = self._calculate_d_limit(error, abs(p_term), d_limit_rules)
                    d_term = max(min(d_term_raw, d_limit), -d_limit)
            else:
                d_term = 0.0

        output = p_term + i_term + d_term
        output = max(min(output, self._max_output), -self._max_output)

        return output, p_term, i_term, d_term, new_integral

    def _log_debug(self, error_x, error_y, p_x, p_y, i_x, i_y, d_x, d_y, out_x, out_y):
        """调试日志"""
        if (abs(error_x) > 10 or abs(error_y) > 10) and self.frame_count % 5 == 0:
            utils.log_debug(
                f"[PID] 误差=({error_x:5.1f},{error_y:5.1f}) | "
                f"P=({p_x:5.2f},{p_y:5.2f}) | I=({i_x:5.2f},{i_y:5.2f}) | "
                f"D=({d_x:5.2f},{d_y:5.2f}) | 输出=({out_x:5.2f},{out_y:5.2f})"
            )

    def calculate(self, error_x, error_y):
        """
        计算双轴PID输出

        Args:
            error_x: X轴误差（目标X - 当前X）
            error_y: Y轴误差（目标Y - 当前Y）

        Returns:
            (output_x, output_y): 双轴控制输出
        """
        current_time = time.perf_counter()
        raw_dt = current_time - self.last_time
        dt = self._get_stable_dt(raw_dt)
        self.last_time = current_time

        self.frame_count += 1

        # 更新误差历史
        self.error_history_x.append(error_x)
        self.error_history_y.append(error_y)

        # X轴计算
        output_x, p_x, i_x, d_x, self.integral_x = self._calculate_axis_output(
            error_x, self.error_history_x, self.integral_x,
            self.kp_x, self.ki_x, self.kd_x,
            self._d_limit_rules_x, dt
        )

        # Y轴计算（独立参数）
        output_y, p_y, i_y, d_y, self.integral_y = self._calculate_axis_output(
            error_y, self.error_history_y, self.integral_y,
            self.kp_y, self.ki_y, self.kd_y,
            self._d_limit_rules_y, dt
        )

        self.first_call = False

        # 日志
        self._maybe_log(error_x, error_y, p_x, p_y, i_x, i_y, d_x, d_y, output_x, output_y)

        return output_x, output_y

    def get_params(self):
        """获取当前参数（调试用）"""
        return {
            'x': {'kp': self.kp_x, 'ki': self.ki_x, 'kd': self.kd_x},
            'y': {'kp': self.kp_y, 'ki': self.ki_y, 'kd': self.kd_y}
        }
