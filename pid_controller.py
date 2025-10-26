import time


class PIDController:
    """
    自适应PID控制器

    根据误差大小动态调整参数
    """

    def __init__(self, kp=0.45, ki=0.0, kd=0.08):  # 🆕 base_kp上调
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

        # 🆕 升级分段：近距离更激进（高Kp，低Kd防震荡）
        self.distance_thresholds = [
            # (距离阈值, Kp倍数, Kd倍数)
            (3, 1.0, 0.5),   # <3px: 全速收敛，低Kd防抖
            (10, 0.8, 0.8),  # <10px: 加速接近
            (30, 1.0, 1.0),  # <30px: 平衡
            (float('inf'), 1.2, 0.8)  # >30px: 快速
        ]

        # 🆕 反过冲：临时降Kp（外部传入反馈）
        self.anti_overshoot_factor = 1.0  # 初始1.0，过冲后降到0.7

        # 限制
        self.integral_limit = 50
        self.output_limit = 25  # 🆕 微调：从20上到25，容忍中距

    def reset(self):
        """重置内部状态"""
        self.last_error_x = 0
        self.last_error_y = 0
        self.integral_x = 0
        self.integral_y = 0
        self.last_time = time.time()
        self.anti_overshoot_factor = 1.0  # 🆕 重置反过冲

    def apply_anti_overshoot(self, overshot: bool):
        """🆕 反过冲补偿：检测过冲后降Kp"""
        if overshot:
            self.anti_overshoot_factor = 0.7  # 临时保守
        else:
            self.anti_overshoot_factor = min(1.0, self.anti_overshoot_factor + 0.1)  # 渐恢复

    def _get_adaptive_params(self, distance):
        """
        根据距离获取自适应参数

        返回: (kp, kd)
        """
        for threshold, kp_mult, kd_mult in self.distance_thresholds:
            if distance < threshold:
                kp = self.base_kp * kp_mult * self.anti_overshoot_factor  # 🆕 乘反过冲因子
                kd = self.base_kd * kd_mult
                return kp, kd

        # 默认返回基础参数
        return self.base_kp * self.anti_overshoot_factor, self.base_kd

    def calculate(self, error_x, error_y):
        current_time = time.time()
        dt = current_time - self.last_time
        if dt <= 0:
            dt = 0.001
        self.last_time = current_time

        distance = (error_x ** 2 + error_y ** 2) ** 0.5
        kp, kd = self._get_adaptive_params(distance)

        # ========== X轴 ==========
        p_term_x = kp * error_x

        derivative_x = (error_x - self.last_error_x) / dt
        if abs(derivative_x) > 1000:
            derivative_x = 0

        # 🆕 D项独立限幅（防止单轴爆炸）
        d_term_x = kd * derivative_x
        d_term_x = max(min(d_term_x, 3.0), -3.0)  # D项限制在±3px

        self.last_error_x = error_x
        output_x = p_term_x + d_term_x

        # ========== Y轴（同样逻辑）==========
        p_term_y = kp * error_y

        derivative_y = (error_y - self.last_error_y) / dt
        if abs(derivative_y) > 1000:
            derivative_y = 0

        # 🆕 Y轴D项限幅（关键修复）
        d_term_y = kd * derivative_y
        d_term_y = max(min(d_term_y, 3.0), -3.0)  # ← 防止-21px的D项

        self.last_error_y = error_y
        output_y = p_term_y + d_term_y

        # 总输出限幅
        output_x = max(min(output_x, 50), -50)
        output_y = max(min(output_y, 50), -50)

        return output_x, output_y