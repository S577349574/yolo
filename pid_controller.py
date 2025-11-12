import time
from collections import deque

from config_manager import get_config
import utils


class PIDController:
    """简化版PID控制器（修复D项震荡问题）"""

    def __init__(self, kp=0.95, ki=0.0, kd=0.05):
        self.kp = kp
        self.ki = ki
        self.kd = kd

        self.last_error_x = 0
        self.last_error_y = 0
        self.integral_x = 0
        self.integral_y = 0
        self.last_time = time.perf_counter()

        # 时间戳平滑
        self.dt_history = deque(maxlen=5)

        # 🔥 首次调用标志
        self.first_call = True

        # 🔥 误差历史（用于更稳定的D项计算）
        self.error_history_x = deque(maxlen=3)
        self.error_history_y = deque(maxlen=3)

        # 调试
        self.debug_enabled = get_config('ENABLE_LOGGING', False)
        self.frame_count = 0

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

    def calculate(self, error_x, error_y):
        """计算PID输出（修复版）"""
        current_time = time.perf_counter()
        raw_dt = current_time - self.last_time
        dt = self._get_stable_dt(raw_dt)
        self.last_time = current_time

        self.frame_count += 1

        # ========== X轴 ==========
        p_term_x = self.kp * error_x

        # 🔥 使用多帧平均计算D项（避免单帧噪声）
        self.error_history_x.append(error_x)

        if self.first_call or len(self.error_history_x) < 2:
            d_term_x = 0.0
        else:
            # 使用首尾误差计算平均变化率
            errors = list(self.error_history_x)
            time_span = dt * (len(errors) - 1)
            derivative_x = (errors[-1] - errors[0]) / time_span if time_span > 0 else 0

            # 🔥 关键修复：限制微分变化率（更保守）
            max_derivative = 1500  # 降低到1500 px/s
            derivative_x = max(min(derivative_x, max_derivative), -max_derivative)

            # 计算D项
            d_term_x_raw = self.kd * derivative_x

            # 🔥 动态限幅：根据误差大小和P项强度
            p_magnitude = abs(p_term_x)

            # D项最大不超过P项的1.5倍（避免过度阻尼）
            if abs(error_x) > 30:
                d_limit = min(p_magnitude * 1.5, 15.0)
            elif abs(error_x) > 15:
                d_limit = min(p_magnitude * 1.2, 8.0)
            else:
                d_limit = min(p_magnitude * 0.8, 3.0)  # 精细控制时D项更小

            d_term_x = max(min(d_term_x_raw, d_limit), -d_limit)

            # 🔥 死区：误差变化极小时不施加D项（减少震荡）
            if abs(derivative_x) < 50:  # 变化率 < 50 px/s
                d_term_x = 0.0

        output_x = p_term_x + d_term_x

        # ========== Y轴（同样逻辑）==========
        p_term_y = self.kp * error_y

        self.error_history_y.append(error_y)

        if self.first_call or len(self.error_history_y) < 2:
            d_term_y = 0.0
            self.first_call = False
        else:
            errors = list(self.error_history_y)
            time_span = dt * (len(errors) - 1)
            derivative_y = (errors[-1] - errors[0]) / time_span if time_span > 0 else 0

            derivative_y = max(min(derivative_y, 1500), -1500)
            d_term_y_raw = self.kd * derivative_y

            p_magnitude = abs(p_term_y)

            if abs(error_y) > 30:
                d_limit = min(p_magnitude * 1.5, 15.0)
            elif abs(error_y) > 15:
                d_limit = min(p_magnitude * 1.2, 8.0)
            else:
                d_limit = min(p_magnitude * 0.8, 3.0)

            d_term_y = max(min(d_term_y_raw, d_limit), -d_limit)

            if abs(derivative_y) < 50:
                d_term_y = 0.0

        output_y = p_term_y + d_term_y

        # 总输出限幅
        max_output = get_config("MAX_SINGLE_MOVE_PX", 300)
        output_x = max(min(output_x, max_output), -max_output)
        output_y = max(min(output_y, max_output), -max_output)

        # 🔥 简化的调试输出
        if self.debug_enabled and (abs(error_x) > 10 or abs(error_y) > 10):
            if self.frame_count % 5 == 0:  # 每5帧输出一次
                utils.log(
                    f"[PID] "
                    f"误差=({error_x:5.1f},{error_y:5.1f}) | "
                    f"P=({p_term_x:5.2f},{p_term_y:5.2f}) | "
                    f"D=({d_term_x:5.2f},{d_term_y:5.2f}) | "
                    f"输出=({output_x:5.2f},{output_y:5.2f})"
                )

        return output_x, output_y
