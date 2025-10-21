"""PID控制器（分段参数版）"""
import time


class PIDController:
    """
    自适应PID控制器

    根据误差大小动态调整参数
    """

    def __init__(self, kp=0.4, ki=0.0, kd=0.08):
        """
        初始化PID控制器

        参数:
            kp: 基础比例系数
            ki: 积分系数（建议保持0）
            kd: 基础微分系数
        """
        self.base_kp = kp
        self.base_ki = ki
        self.base_kd = kd

        # 内部状态
        self.last_error_x = 0
        self.last_error_y = 0
        self.integral_x = 0
        self.integral_y = 0
        self.last_time = time.time()

        # 🆕 分段参数配置
        self.distance_thresholds = [
            # (距离阈值, Kp倍数, Kd倍数)
            (5, 0.2, 1.5),  # <5px:  极保守，强制动（防止震荡）
            (15, 0.5, 1.2),  # <15px: 保守接近
            (40, 1.0, 1.0),  # <40px: 正常移动
            (float('inf'), 1.3, 0.8)  # >40px: 快速接近
        ]

        # 限制
        self.integral_limit = 50
        self.output_limit = 20

    def reset(self):
        """重置内部状态"""
        self.last_error_x = 0
        self.last_error_y = 0
        self.integral_x = 0
        self.integral_y = 0
        self.last_time = time.time()

    def _get_adaptive_params(self, distance):
        """
        根据距离获取自适应参数

        返回: (kp, kd)
        """
        for threshold, kp_mult, kd_mult in self.distance_thresholds:
            if distance < threshold:
                return self.base_kp * kp_mult, self.base_kd * kd_mult

        # 默认返回基础参数
        return self.base_kp, self.base_kd

    def calculate(self, error_x, error_y):
        """
        计算PID输出（自适应参数）

        参数:
            error_x: X轴误差
            error_y: Y轴误差

        返回:
            (output_x, output_y): 应该移动的像素数
        """
        # 计算时间间隔
        current_time = time.time()
        dt = current_time - self.last_time
        if dt <= 0:
            dt = 0.001
        self.last_time = current_time

        # 🆕 计算距离，动态调整参数
        distance = (error_x**2 + error_y**2)**0.5
        kp, kd = self._get_adaptive_params(distance)

        # === X轴计算 ===
        # P项
        p_term_x = kp * error_x

        # I项（保持禁用）
        self.integral_x += error_x * dt
        self.integral_x = max(min(self.integral_x, self.integral_limit), -self.integral_limit)
        i_term_x = self.base_ki * self.integral_x

        # D项
        derivative_x = (error_x - self.last_error_x) / dt
        # 🆕 微分限幅（防止噪声放大）
        derivative_x = max(min(derivative_x, 100), -100)
        d_term_x = kd * derivative_x

        self.last_error_x = error_x

        output_x = p_term_x + i_term_x + d_term_x

        # === Y轴计算 ===
        p_term_y = kp * error_y

        self.integral_y += error_y * dt
        self.integral_y = max(min(self.integral_y, self.integral_limit), -self.integral_limit)
        i_term_y = self.base_ki * self.integral_y

        derivative_y = (error_y - self.last_error_y) / dt
        derivative_y = max(min(derivative_y, 100), -100)  # 微分限幅
        d_term_y = kd * derivative_y

        self.last_error_y = error_y

        output_y = p_term_y + i_term_y + d_term_y

        # 输出限幅
        output_x = max(min(output_x, self.output_limit), -self.output_limit)
        output_y = max(min(output_y, self.output_limit), -self.output_limit)

        return output_x, output_y
