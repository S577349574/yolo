import time
from collections import deque
from typing import Callable
import utils


class PIDController:
    """双轴独立参数PID控制器（支持热重载）"""

    def __init__(self,
                 kp_x=None, ki_x=None, kd_x=None,
                 kp_y=None, ki_y=None, kd_y=None,
                 auto_reload=True):
        """
        初始化双轴PID控制器

        Args:
            auto_reload: 是否注册热重载回调
        """
        # ⭐ 延迟导入，避免循环依赖
        from config_manager import get_config

        # X轴参数
        self.kp_x = kp_x if kp_x is not None else get_config("PID_KP_X", 0.2)
        self.ki_x = ki_x if ki_x is not None else get_config("PID_KI_X", 0.02)
        self.kd_x = kd_x if kd_x is not None else get_config("PID_KD_X", 0.05)

        # Y轴参数
        self.kp_y = kp_y if kp_y is not None else get_config("PID_KP_Y", 0.4)
        self.ki_y = ki_y if ki_y is not None else get_config("PID_KI_Y", 0.0)
        self.kd_y = kd_y if kd_y is not None else get_config("PID_KD_Y", 0.06)

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
        self._max_integral = get_config("PID_MAX_INTEGRAL", 100)

        # D项限幅规则表
        self._d_limit_rules_x = [
            (30, 1.5, 15.0),
            (15, 1.2, 8.0),
            (0, 0.8, 3.0)
        ]
        self._d_limit_rules_y = [
            (30, 1.8, 18.0),
            (15, 1.4, 10.0),
            (0, 1.0, 4.0)
        ]

        self.frame_count = 0

        # 条件编译日志
        if get_config('ENABLE_LOGGING', False):
            self._maybe_log = self._log_debug
        else:
            self._maybe_log = lambda *args: None

        # ⭐ 注册热重载
        if auto_reload:
            self._register_hot_reload()

    def _register_hot_reload(self):
        """注册热重载回调"""
        try:
            from config_manager import on_config_change

            # ⭐ 使用闭包捕获 self，确保回调正确更新实例属性
            on_config_change("PID_KP_X", lambda v: self._update_param('kp_x', v))
            on_config_change("PID_KI_X", lambda v: self._update_param('ki_x', v))
            on_config_change("PID_KD_X", lambda v: self._update_param('kd_x', v))
            on_config_change("PID_KP_Y", lambda v: self._update_param('kp_y', v))
            on_config_change("PID_KI_Y", lambda v: self._update_param('ki_y', v))
            on_config_change("PID_KD_Y", lambda v: self._update_param('kd_y', v))
            on_config_change("MAX_SINGLE_MOVE_PX", lambda v: self._update_param('_max_output', v))

            utils.log("[PID] ✅ 热重载回调已注册")
        except Exception as e:
            utils.log(f"[PID] ⚠ 热重载注册失败: {e}")

    def _update_param(self, attr_name: str, value):
        """更新参数并记录日志"""
        old_value = getattr(self, attr_name, None)
        setattr(self, attr_name, value)
        utils.log(f"[PID] 🔄 {attr_name}: {old_value} → {value}")

    # ... 其余方法保持不变 ...

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
        """动态调整PID参数"""
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
        """单轴PID计算"""
        p_term = kp * error

        new_integral = integral
        if ki > 0:
            new_integral = integral + error * dt
            new_integral = max(-self._max_integral, min(self._max_integral, new_integral))
            if abs(error) > 50:
                new_integral = integral
            i_term = ki * new_integral
        else:
            i_term = 0.0

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
        """计算双轴PID输出"""
        current_time = time.perf_counter()
        raw_dt = current_time - self.last_time
        dt = self._get_stable_dt(raw_dt)
        self.last_time = current_time

        self.frame_count += 1

        self.error_history_x.append(error_x)
        self.error_history_y.append(error_y)

        output_x, p_x, i_x, d_x, self.integral_x = self._calculate_axis_output(
            error_x, self.error_history_x, self.integral_x,
            self.kp_x, self.ki_x, self.kd_x,
            self._d_limit_rules_x, dt
        )

        output_y, p_y, i_y, d_y, self.integral_y = self._calculate_axis_output(
            error_y, self.error_history_y, self.integral_y,
            self.kp_y, self.ki_y, self.kd_y,
            self._d_limit_rules_y, dt
        )

        self.first_call = False
        self._maybe_log(error_x, error_y, p_x, p_y, i_x, i_y, d_x, d_y, output_x, output_y)

        return output_x, output_y

    def get_params(self):
        """获取当前参数"""
        return {
            'x': {'kp': self.kp_x, 'ki': self.ki_x, 'kd': self.kd_x},
            'y': {'kp': self.kp_y, 'ki': self.ki_y, 'kd': self.kd_y}
        }
