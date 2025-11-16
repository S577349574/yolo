import time
from collections import deque
from config_manager import get_config
import utils


class PIDController:
    """优化版PID控制器"""

    def __init__(self, kp=0.95, ki=0.0, kd=0.05):
        self.kp = kp
        self.ki = ki
        self.kd = kd

        self.last_error_x = 0
        self.last_error_y = 0
        self.integral_x = 0
        self.integral_y = 0
        self.last_time = time.perf_counter()

        self.dt_history = deque(maxlen=5)
        self.first_call = True

        self.error_history_x = deque(maxlen=3)
        self.error_history_y = deque(maxlen=3)

        # ✅ 预计算常量
        self._max_derivative = 1500
        self._derivative_deadzone = 50
        self._max_output = get_config("MAX_SINGLE_MOVE_PX", 300)

        # D项限幅规则表
        self._d_limit_rules = [
            (30, 1.5, 15.0),
            (15, 1.2, 8.0),
            (0, 0.8, 3.0)
        ]

        # ✅ 条件编译日志
        self.frame_count = 0
        if get_config('ENABLE_LOGGING', False):
            self._maybe_log = self._log_debug
        else:
            self._maybe_log = lambda *args: None

    def reset(self):
        """重置PID状态"""
        self.last_error_x = 0
        self.last_error_y = 0
        self.integral_x = 0
        self.integral_y = 0
        self.last_time = time.perf_counter()
        self.dt_history.clear()
        self.first_call = True
        self.error_history_x.clear()
        self.error_history_y.clear()
        self.frame_count = 0

    def _get_stable_dt(self, raw_dt):
        """平滑时间差"""
        if raw_dt <= 0 or raw_dt > 0.5:
            raw_dt = 0.016

        self.dt_history.append(raw_dt)
        sorted_dt = sorted(self.dt_history)
        return sorted_dt[len(sorted_dt) // 2]

    def _calculate_d_limit(self, error, p_magnitude):
        """快速计算D项限幅"""
        abs_error = abs(error)
        for threshold, factor, max_val in self._d_limit_rules:
            if abs_error > threshold:
                return min(p_magnitude * factor, max_val)
        return 3.0  # 默认最小限幅

    def _calculate_axis_output(self, error, error_history, dt):
        """单轴PID计算（避免重复代码）"""
        p_term = self.kp * error

        # D项计算
        if self.first_call or len(error_history) < 2:
            d_term = 0.0
        else:
            # ✅ 直接索引访问（避免 list() 拷贝）
            first_error = error_history[0]
            last_error = error_history[-1]
            time_span = dt * (len(error_history) - 1)

            if time_span > 0:
                derivative = (last_error - first_error) / time_span
                derivative = max(min(derivative, self._max_derivative), -self._max_derivative)

                # 死区检查
                if abs(derivative) < self._derivative_deadzone:
                    d_term = 0.0
                else:
                    d_term_raw = self.kd * derivative
                    d_limit = self._calculate_d_limit(error, abs(p_term))
                    d_term = max(min(d_term_raw, d_limit), -d_limit)
            else:
                d_term = 0.0

        output = p_term + d_term
        return (
            max(min(output, self._max_output), -self._max_output),
            p_term,
            d_term
        )

    def _log_debug(self, error_x, error_y, p_x, p_y, d_x, d_y, out_x, out_y):
        """真实的日志函数"""
        if (abs(error_x) > 10 or abs(error_y) > 10) and self.frame_count % 5 == 0:
            utils.log_debug(
                f"[PID] 误差=({error_x:5.1f},{error_y:5.1f}) | "
                f"P=({p_x:5.2f},{p_y:5.2f}) | D=({d_x:5.2f},{d_y:5.2f}) | "
                f"输出=({out_x:5.2f},{out_y:5.2f})"
            )

    def calculate(self, error_x, error_y):
        """计算PID输出（优化版）"""
        current_time = time.perf_counter()
        raw_dt = current_time - self.last_time
        dt = self._get_stable_dt(raw_dt)
        self.last_time = current_time

        self.frame_count += 1

        # 更新误差历史
        self.error_history_x.append(error_x)
        self.error_history_y.append(error_y)

        # 分别计算两轴
        output_x, p_term_x, d_term_x = self._calculate_axis_output(error_x, self.error_history_x, dt)
        output_y, p_term_y, d_term_y = self._calculate_axis_output(error_y, self.error_history_y, dt)

        self.first_call = False

        # ✅ 零开销日志
        self._maybe_log(error_x, error_y, p_term_x, p_term_y, d_term_x, d_term_y, output_x, output_y)

        return output_x, output_y
