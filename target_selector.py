# target_selector.py (完整修复版 - 支持真实准星位置)

import math
from typing import List, Dict, Optional, Tuple

import numpy as np

import utils
from config_manager import get_config


class TargetKalmanFilter:
    """目标追踪卡尔曼滤波器"""

    def __init__(self, process_noise: float = 0.1, measurement_noise: float = 5.0):
        # 状态: [x, y, vx, vy]
        self.state = np.zeros(4, dtype=np.float32)

        # 状态转移矩阵
        self.dt = 1 / 60
        self.F = np.array([
            [1, 0, self.dt, 0],
            [0, 1, 0, self.dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ], dtype=np.float32)

        # 观测矩阵
        self.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ], dtype=np.float32)

        # 协方差
        self.P = np.eye(4, dtype=np.float32) * 100
        self.Q = np.eye(4, dtype=np.float32) * process_noise
        self.R = np.eye(2, dtype=np.float32) * measurement_noise

        self.initialized = False
        self.frames_without_update = 0

    def reset(self):
        """重置滤波器"""
        self.state = np.zeros(4, dtype=np.float32)
        self.P = np.eye(4, dtype=np.float32) * 100
        self.initialized = False
        self.frames_without_update = 0

    def init_with_position(self, x: float, y: float):
        """用初始位置初始化"""
        self.state = np.array([x, y, 0, 0], dtype=np.float32)
        self.P = np.eye(4, dtype=np.float32) * 100
        self.initialized = True
        self.frames_without_update = 0

    def update(self, measured_x: float, measured_y: float) -> Tuple[float, float]:
        """用观测值更新状态，返回滤波后的位置"""

        if not self.initialized:
            self.init_with_position(measured_x, measured_y)
            return measured_x, measured_y

        # 预测
        state_pred = self.F @ self.state
        P_pred = self.F @ self.P @ self.F.T + self.Q

        # 更新
        z = np.array([measured_x, measured_y], dtype=np.float32)
        y = z - self.H @ state_pred
        S = self.H @ P_pred @ self.H.T + self.R
        K = P_pred @ self.H.T @ np.linalg.inv(S)

        self.state = state_pred + K @ y
        self.P = (np.eye(4, dtype=np.float32) - K @ self.H) @ P_pred

        self.frames_without_update = 0

        return float(self.state[0]), float(self.state[1])

    def predict_only(self, max_frames: int = 5) -> Optional[Tuple[float, float]]:
        """仅预测（无观测时调用）"""

        if not self.initialized:
            return None

        self.frames_without_update += 1

        if self.frames_without_update > max_frames:
            return None

        # 只预测
        self.state = self.F @ self.state
        self.P = self.F @ self.P @ self.F.T + self.Q

        return float(self.state[0]), float(self.state[1])

    def get_velocity(self) -> Tuple[float, float]:
        """获取当前估计速度"""
        if self.initialized:
            return float(self.state[2]), float(self.state[3])
        return 0.0, 0.0

    def get_predicted_position(self, frames_ahead: int = 1) -> Optional[Tuple[float, float]]:
        """预测未来位置（不修改状态）"""
        if not self.initialized:
            return None

        # 使用当前速度预测
        pred_x = self.state[0] + self.state[2] * self.dt * frames_ahead
        pred_y = self.state[1] + self.state[3] * self.dt * frames_ahead

        return float(pred_x), float(pred_y)


class TargetSelector:
    """目标选择器：按目标个体分组，优先选择最大框目标"""

    def __init__(self):
        # 基础跟踪状态
        self.last_target_x: Optional[int] = None
        self.last_target_y: Optional[int] = None
        self.frames_without_target: int = 0
        self.is_locked: bool = False

        # 目标锁定（目标组级别）
        self.locked_target_group_id: Optional[str] = None
        self.target_lock_frames: int = 0

        # 瞄准点平滑（EMA方式）
        self.smoothed_aim_x: Optional[float] = None
        self.smoothed_aim_y: Optional[float] = None

        # 卡尔曼滤波器
        self.kalman_filter = TargetKalmanFilter(
            process_noise=get_config('KALMAN_PROCESS_NOISE', 0.1),
            measurement_noise=get_config('KALMAN_MEASUREMENT_NOISE', 5.0)
        )
        self.use_kalman = get_config('USE_KALMAN_FILTER', True)

    def calculate_aim_point(
            self,
            box: Tuple[float, float, float, float],
            capture_area: Dict[str, int]
    ) -> Tuple[int, int]:
        """计算瞄准点在全局屏幕坐标系中的位置"""
        x1, y1, x2, y2 = map(int, box)
        box_width = x2 - x1
        box_height = y2 - y1

        y_ratio = get_config('AIM_Y_RATIO', 0.5)
        x_offset = get_config('AIM_X_OFFSET', 0.5)

        center_x_cropped = int(x1 + box_width * x_offset)
        center_y_cropped = int(y1 + box_height * y_ratio)

        target_x = capture_area['left'] + center_x_cropped
        target_y = capture_area['top'] + center_y_cropped

        return target_x, target_y

    def _group_detections_by_target(
            self,
            detections: List[Dict],
            reference_x: float,  # ⭐ 修改：接受真实准星位置
            reference_y: float
    ) -> Dict[str, List[Dict]]:
        """
        将检测框按目标个体分组

        逻辑：如果身体和头部距离很近，认为是同一个目标

        返回: {group_id: [detection1, detection2, ...]}
        """
        group_distance_threshold = get_config('TARGET_GROUP_DISTANCE_THRESHOLD', 100)
        groups: Dict[str, List[Dict]] = {}
        next_group_id = 0

        # 先按类别分类
        bodies = [d for d in detections if d.get('class_id') == 0]
        heads = [d for d in detections if d.get('class_id') == 1]

        # ⭐ 修改：使用真实准星位置计算距离
        for detection in detections:
            detection['distance_to_center'] = math.hypot(
                detection['x'] - reference_x,
                detection['y'] - reference_y
            )

            # 计算面积
            box = detection.get('box', (0, 0, 0, 0))
            x1, y1, x2, y2 = box
            area = (x2 - x1) * (y2 - y1)
            detection['box_area'] = area

        # 为每个身体创建一个组
        for body in bodies:
            group_id = f"target_{next_group_id}"
            next_group_id += 1
            groups[group_id] = [body]

        # 尝试将头部分配到最近的身体组
        for head in heads:
            # 找最近的身体
            closest_group = None
            min_distance = float('inf')

            for group_id, group_detections in groups.items():
                body = group_detections[0]
                distance = math.hypot(head['x'] - body['x'], head['y'] - body['y'])

                if distance < min_distance and distance < group_distance_threshold:
                    min_distance = distance
                    closest_group = group_id

            if closest_group:
                groups[closest_group].append(head)
            else:
                group_id = f"target_{next_group_id}"
                next_group_id += 1
                groups[group_id] = [head]

        return groups

    def select_best_target(
            self,
            candidate_targets: List[Dict],
            screen_width: int,
            screen_height: int,
            reference_x: Optional[float] = None,  # ⭐ 新增：真实准星X
            reference_y: Optional[float] = None  # ⭐ 新增：真实准星Y
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        目标选择：先按目标个体分组，再选择类别

        Args:
            candidate_targets: 候选目标列表
            screen_width: 屏幕宽度
            screen_height: 屏幕高度
            reference_x: 真实准星X坐标（如果为None则使用屏幕中心）
            reference_y: 真实准星Y坐标（如果为None则使用屏幕中心）
        """

        max_lost_frames = get_config('MAX_LOST_FRAMES', 30)

        # ⭐ 确定参考点（准星位置）
        if reference_x is None or reference_y is None:
            reference_x = screen_width // 2
            reference_y = screen_height // 2

        # ===== 1. 无目标处理 =====
        if not candidate_targets:
            self.frames_without_target += 1

            if self.frames_without_target >= max_lost_frames:
                self._reset_tracking()
                return None, None

            # 卡尔曼预测
            if self.use_kalman and self.is_locked:
                predicted = self.kalman_filter.predict_only(
                    max_frames=get_config('KALMAN_MAX_PREDICT_FRAMES', 5)
                )

                if predicted is not None:
                    pred_x, pred_y = predicted
                    pred_x = max(0, min(int(pred_x), screen_width - 1))
                    pred_y = max(0, min(int(pred_y), screen_height - 1))

                    self.last_target_x = pred_x
                    self.last_target_y = pred_y

                    if get_config('DEBUG_MODE', False):
                        utils.log_debug(f"[卡尔曼预测] ({pred_x}, {pred_y})")

                    return pred_x, pred_y

            return None, None

        # ===== 2. 目标分组（使用真实准星位置）=====
        target_groups = self._group_detections_by_target(
            candidate_targets,
            reference_x,  # ⭐ 传入真实准星位置
            reference_y
        )

        # 计算每个目标组的代表距离
        group_info = []
        for group_id, detections in target_groups.items():
            representative = max(detections, key=lambda d: d['box_area'])
            group_info.append({
                'group_id': group_id,
                'detections': detections,
                'distance': representative['distance_to_center'],
                'representative': representative
            })

        group_info.sort(key=lambda g: g['distance'])
        if not group_info:
            self.frames_without_target += 1
            if self.frames_without_target >= max_lost_frames:
                self._reset_tracking()
            return None, None

        closest_group = group_info[0]
        selected_group_id = closest_group['group_id']

        # ===== 3. 锁定稳定性检查 =====
        min_lock_frames = get_config('MIN_TARGET_LOCK_FRAMES', 10)
        target_identity_distance = get_config('TARGET_IDENTITY_DISTANCE', 100)
        switch_distance_threshold = get_config('TARGET_SWITCH_DISTANCE_THRESHOLD', 50)

        locked_group = None
        if self.locked_target_group_id is not None and self.last_target_x is not None:
            for group in group_info:
                if group['group_id'] == self.locked_target_group_id:
                    rep = group['representative']
                    position_diff = math.hypot(
                        rep['x'] - self.last_target_x,
                        rep['y'] - self.last_target_y
                    )
                    if position_diff < target_identity_distance:
                        locked_group = group
                        break

            if locked_group is not None:
                distance_gain = locked_group['distance'] - closest_group['distance']
                should_keep_lock = False

                if self.target_lock_frames < min_lock_frames:
                    should_keep_lock = True
                    reason = f"锁定时间不足 ({self.target_lock_frames} < {min_lock_frames})"
                elif distance_gain < switch_distance_threshold:
                    should_keep_lock = True
                    reason = f"距离优势不足 ({distance_gain:.0f}px < {switch_distance_threshold}px)"

                if should_keep_lock:
                    selected_group_id = locked_group['group_id']
                    closest_group = locked_group

                    if get_config('DEBUG_MODE', False):
                        utils.log_debug(f"[保持锁定] {reason}")

        # ===== 4. 组内部位选择 =====
        selected_group_detections = closest_group['detections']

        heads = []
        bodies = []
        head_class_id = get_config('HEAD_CLASS_ID', 1)

        for detection in selected_group_detections:
            if detection.get('class_id') == head_class_id:
                heads.append(detection)
            else:
                bodies.append(detection)

        # 头部过滤
        valid_heads = []
        if get_config('IGNORE_SMALL_TARGET_HEAD', True):
            small_area_threshold = get_config('SMALL_TARGET_AREA_THRESHOLD', 200)  # 例如 20×40=800
            for head in heads:
                box = head.get('box', (0, 0, 0, 0))
                x1, y1, x2, y2 = box
                box_width = x2 - x1
                box_height = y2 - y1
                box_area = box_width * box_height

                if box_area >= small_area_threshold:
                    valid_heads.append(head)
                elif get_config('DEBUG_MODE', False):
                    utils.log_debug(
                        f"[过滤小头部] 面积:{box_area:.0f}px² < {small_area_threshold}px²"
                    )
        else:
            valid_heads = heads

        if get_config('ENABLE_HEAD_PRIORITY', True) and valid_heads:
            selected_detection = min(valid_heads, key=lambda d: d['distance_to_center'])
            selected_part_type = 'head'

            if get_config('DEBUG_MODE', False):
                utils.log_debug(
                    f"[组内选择] 头部优先 | "
                    f"头部数:{len(valid_heads)} | "
                    f"距离:{selected_detection['distance_to_center']:.0f}px"
                )

        elif bodies:
            selected_detection = min(bodies, key=lambda d: d['distance_to_center'])
            selected_part_type = 'body'

            if get_config('DEBUG_MODE', False):
                reason = "无有效头部" if heads else "头部被过滤"
                utils.log_debug(
                    f"[组内选择] 回退身体 | "
                    f"原因:{reason} | "
                    f"距离:{selected_detection['distance_to_center']:.0f}px"
                )

        else:
            selected_detection = min(
                selected_group_detections,
                key=lambda d: d['distance_to_center']
            )
            selected_part_type = 'fallback'

            if get_config('DEBUG_MODE', False):
                utils.log_debug(f"[组内选择] 兜底策略")

        # ===== 5. 更新锁定状态 =====
        is_new_target = (selected_group_id != self.locked_target_group_id)

        if is_new_target:
            self.locked_target_group_id = selected_group_id
            self.target_lock_frames = 0

            group_composition = [
                "头" if d.get('class_id') == head_class_id else "身"
                for d in selected_group_detections
            ]

            utils.log_debug(
                f"✓ 锁定目标组 | {selected_group_id} | "
                f"组成:[{'+'.join(group_composition)}] | "
                f"选择:{selected_part_type} | "
                f"距离:{selected_detection['distance_to_center']:.0f}px"
            )
        else:
            self.target_lock_frames += 1

            if get_config('DEBUG_MODE', False):
                utils.log_debug(
                    f"[组内稳定] 锁定{self.target_lock_frames}帧 | "
                    f"当前部位:{selected_part_type}"
                )

        # ===== 6. 应用平滑 =====
        if 'aim_x' in selected_detection and 'aim_y' in selected_detection:
            raw_x = selected_detection['aim_x']
            raw_y = selected_detection['aim_y']
        else:
            raw_x = selected_detection['x']
            raw_y = selected_detection['y']

        smoothed_x, smoothed_y = self._apply_smoothing(raw_x, raw_y, is_new_target)

        smoothed_x = max(0, min(smoothed_x, screen_width - 1))
        smoothed_y = max(0, min(smoothed_y, screen_height - 1))

        self.last_target_x = int(smoothed_x)
        self.last_target_y = int(smoothed_y)
        self.frames_without_target = 0
        self.is_locked = True

        return self.last_target_x, self.last_target_y

    def _apply_smoothing(
            self,
            raw_x: float,
            raw_y: float,
            is_new_target: bool = False
    ) -> Tuple[int, int]:
        """平滑处理 - 支持 EMA 或卡尔曼"""

        if self.use_kalman:
            if is_new_target:
                self.kalman_filter.init_with_position(raw_x, raw_y)
                return int(raw_x), int(raw_y)

            smooth_x, smooth_y = self.kalman_filter.update(raw_x, raw_y)

            if get_config('DEBUG_MODE', False):
                delta_x = abs(smooth_x - raw_x)
                delta_y = abs(smooth_y - raw_y)
                if delta_x > 5 or delta_y > 5:
                    utils.log_debug(
                        f"[卡尔曼平滑] 原始({raw_x:.0f},{raw_y:.0f}) → "
                        f"平滑({smooth_x:.0f},{smooth_y:.0f})"
                    )

            return int(smooth_x), int(smooth_y)

        else:
            smooth_alpha = get_config('AIM_POINT_SMOOTH_ALPHA', 0.25)

            if is_new_target or self.smoothed_aim_x is None:
                self.smoothed_aim_x = float(raw_x)
                self.smoothed_aim_y = float(raw_y)
            else:
                self.smoothed_aim_x = (
                        smooth_alpha * raw_x +
                        (1 - smooth_alpha) * self.smoothed_aim_x
                )
                self.smoothed_aim_y = (
                        smooth_alpha * raw_y +
                        (1 - smooth_alpha) * self.smoothed_aim_y
                )

            return int(self.smoothed_aim_x), int(self.smoothed_aim_y)

    def should_send_command(
            self,
            target_x: int,
            target_y: int,
            reference_x: float,  # ⭐ 修改：接受真实准星位置
            reference_y: float
    ) -> bool:
        """
        判断是否需要发送移动命令

        Args:
            target_x: 目标X坐标
            target_y: 目标Y坐标
            reference_x: 真实准星X坐标
            reference_y: 真实准星Y坐标
        """
        offset_x = target_x - reference_x
        offset_y = target_y - reference_y
        offset_distance = math.hypot(offset_x, offset_y)

        precision_dead_zone = get_config('PRECISION_DEAD_ZONE', 2)
        return offset_distance >= precision_dead_zone

    def get_lead_target(
            self,
            current_x: int,
            current_y: int,
            lead_frames: int = 2
    ) -> Tuple[int, int]:
        """获取预判位置（用于移动目标）"""

        if not self.use_kalman or not self.kalman_filter.initialized:
            return current_x, current_y

        predicted = self.kalman_filter.get_predicted_position(lead_frames)

        if predicted is None:
            return current_x, current_y

        return int(predicted[0]), int(predicted[1])

    def _reset_tracking(self) -> None:
        """重置所有跟踪状态"""
        self.last_target_x = None
        self.last_target_y = None
        self.is_locked = False
        self.locked_target_group_id = None
        self.target_lock_frames = 0
        self.frames_without_target = 0

        self.smoothed_aim_x = None
        self.smoothed_aim_y = None

        if self.use_kalman:
            self.kalman_filter.reset()

        if get_config('DEBUG_MODE', False):
            utils.log_debug("[重置追踪] 所有状态已清空")
