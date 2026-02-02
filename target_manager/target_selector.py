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
            reference_x: Optional[float] = None,
            reference_y: Optional[float] = None
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        改进版目标选择：基于物理位置持久化的粘性锁定
        """
        # --- 1. 参数与配置准备 ---
        max_lost_frames = get_config('MAX_LOST_FRAMES', 30)
        target_class_ids = get_config('TARGET_CLASS_IDS', [0, 1])
        switch_distance_threshold = get_config('TARGET_SWITCH_DISTANCE_THRESHOLD', 50)  # 切换目标的距离优势阈值
        identity_threshold = get_config('TARGET_IDENTITY_DISTANCE', 80)  # 判定为同一人的最大位移

        # 过滤合法的类别
        candidate_targets = [t for t in candidate_targets if t.get('class_id') in target_class_ids]

        # 确定参考点（准星物理位置）
        if reference_x is None or reference_y is None:
            reference_x = screen_width // 2
            reference_y = screen_height // 2

        # --- 2. 无目标处理 (含卡尔曼预测) ---
        if not candidate_targets:
            self.frames_without_target += 1
            if self.frames_without_target >= max_lost_frames:
                self._reset_tracking()
                return None, None

            if self.use_kalman and self.is_locked:
                predicted = self.kalman_filter.predict_only(max_frames=5)
                if predicted:
                    px, py = map(int, predicted)
                    self.last_target_x, self.last_target_y = px, py
                    return px, py
            return None, None

        # --- 3. 目标分组 ---
        # 内部已根据传入的 reference_x/y 计算了 distance_to_center
        target_groups = self._group_detections_by_target(candidate_targets, reference_x, reference_y)

        # 将字典转为列表并提取特征
        current_groups = []
        for gid, detections in target_groups.items():
            # 找到该组中最具代表性的框（通常是面积最大的身体）
            rep = max(detections, key=lambda d: d['box_area'])
            current_groups.append({
                'id': gid,
                'detections': detections,
                'x': rep['x'],
                'y': rep['y'],
                'dist': rep['distance_to_center'],
                'area': rep['box_area']
            })

        # --- 4. 寻找“老目标”（持久化核心） ---
        best_group = None

        # 如果上一帧已经有锁定的目标，尝试在当前帧找回它
        if self.is_locked and self.last_target_x is not None:
            # 寻找离上一帧瞄准点最近的目标，且位移在合理范围内
            matches = []
            for g in current_groups:
                move_dist = math.hypot(g['x'] - self.last_target_x, g['y'] - self.last_target_y)
                if move_dist < identity_threshold:
                    matches.append((move_dist, g))

            if matches:
                matches.sort(key=lambda x: x[0])
                old_target_now = matches[0][1]

                closest_new = min(current_groups, key=lambda x: x['dist'])

                # 计算当前老目标的优势
                # 只有当新目标比老目标近了 TSDT，并且新目标确实非常靠近准星时才切换
                if closest_new['dist'] < (old_target_now['dist'] - switch_distance_threshold):
                    # 增加一个二次确认：如果老目标还在准星附近（比如 30px 内），即便新目标更近，也不切换
                    if old_target_now['dist'] > 30:
                        best_group = closest_new
                        self.target_lock_frames = 0
                    else:
                        best_group = old_target_now
                else:
                    best_group = old_target_now

        # 如果没有老目标或者跟丢了，选择离当前准星最近的
        if best_group is None:
            current_groups.sort(key=lambda x: x['dist'])
            best_group = current_groups[0]
            self.is_locked = True
            self.target_lock_frames = 0
            self.locked_target_group_id = best_group['id']  # 仅作记录

        # --- 5. 组内部位选择 (头/身) ---
        selected_det, part_name = self._select_part_within_group(best_group['detections'])

        # --- 6. 确定坐标并应用平滑 ---
        raw_x = selected_det.get('aim_x', selected_det['x'])
        raw_y = selected_det.get('aim_y', selected_det['y'])

        # 如果是刚换的目标，重置平滑/卡尔曼以防大幅拉动
        is_new_target = (self.target_lock_frames == 0)
        smoothed_x, smoothed_y = self._apply_smoothing(raw_x, raw_y, is_new_target)

        # 边界约束
        self.last_target_x = max(0, min(int(smoothed_x), screen_width - 1))
        self.last_target_y = max(0, min(int(smoothed_y), screen_height - 1))
        self.frames_without_target = 0


        return self.last_target_x, self.last_target_y

    def _select_part_within_group(self, detections: List[Dict]) -> Tuple[Dict, str]:
        """
        在确定的目标组内选择最佳部位
        """
        head_id = get_config('HEAD_CLASS_ID', 1)
        heads = [d for d in detections if d['class_id'] == head_id]
        bodies = [d for d in detections if d['class_id'] != head_id]

        # 1. 优先尝试头部
        if get_config('ENABLE_HEAD_PRIORITY', True) and heads:
            # 过滤面积太小的头
            if get_config('IGNORE_SMALL_TARGET_HEAD', True):
                threshold = get_config('SMALL_TARGET_AREA_THRESHOLD', 200)
                valid_heads = [h for h in heads if h['box_area'] >= threshold]
                if valid_heads:
                    return min(valid_heads, key=lambda x: x['distance_to_center']), "head"
            else:
                return min(heads, key=lambda x: x['distance_to_center']), "head"

        # 2. 回退到身体
        if bodies:
            return min(bodies, key=lambda x: x['distance_to_center']), "body"

        # 3. 极端情况兜底
        return detections[0], "any"

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
