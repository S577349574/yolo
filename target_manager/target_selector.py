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
    """目标选择器：改进分组与持久化"""

    def __init__(self):
        # 基础跟踪状态
        self.last_target_x: Optional[int] = None
        self.last_target_y: Optional[int] = None
        self.frames_without_target: int = 0
        self.is_locked: bool = False

        self.target_lock_frames: int = 0  # 当前目标已锁定的帧数
        self.locked_target_group_id: Optional[str] = None  # 兼容旧接口
        # ⭐ 新增：目标持久化追踪
        self.tracked_targets: Dict[int, Dict] = {}  # {target_id: {x, y, last_seen_frame, ...}}
        self.current_frame: int = 0
        self.next_target_id: int = 0
        self.locked_target_id: Optional[int] = None

        # 瞄准点平滑
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
        """计算瞄准点 (保持不变)"""
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
            reference_x: float,
            reference_y: float
    ) -> List[Dict]:
        """
        ⭐ 改进版分组：返回目标列表而非字典

        返回格式：
        [
            {
                'x': 中心X,
                'y': 中心Y,
                'body': body_detection or None,
                'head': head_detection or None,
                'distance': 到准星距离,
                'area': 总面积
            },
            ...
        ]
        """
        group_distance_threshold = get_config('TARGET_GROUP_DISTANCE_THRESHOLD', 100)

        # 预处理：计算距离和面积
        for det in detections:
            det['distance_to_center'] = math.hypot(
                det['x'] - reference_x,
                det['y'] - reference_y
            )
            box = det.get('box', (0, 0, 0, 0))
            x1, y1, x2, y2 = box
            det['box_area'] = (x2 - x1) * (y2 - y1)

        bodies = [d for d in detections if d.get('class_id') == 0]
        heads = [d for d in detections if d.get('class_id') == 1]

        target_groups = []

        # ⭐ 改进1：先按身体建组
        for body in bodies:
            target_groups.append({
                'body': body,
                'head': None,
                'x': body['x'],
                'y': body['y'],
                'distance': body['distance_to_center'],
                'area': body['box_area']
            })

        # ⭐ 改进2：头部匹配优化
        used_heads = set()
        for group in target_groups:
            body = group['body']
            best_head = None
            min_distance = float('inf')

            for i, head in enumerate(heads):
                if i in used_heads:
                    continue

                # 距离检查
                distance = math.hypot(head['x'] - body['x'], head['y'] - body['y'])
                if distance > group_distance_threshold:
                    continue

                # ⭐ 新增：头部应该在身体上方（Y坐标更小）
                if head['y'] > body['y'] + 20:  # 允许20px误差
                    continue

                if distance < min_distance:
                    min_distance = distance
                    best_head = head

            if best_head:
                group['head'] = best_head
                used_heads.add(heads.index(best_head))
                # 更新组中心为头部位置（如果有头）
                group['x'] = best_head['x']
                group['y'] = best_head['y']
                group['distance'] = best_head['distance_to_center']
                group['area'] += best_head['box_area']

        # ⭐ 改进3：处理孤立的头部
        for i, head in enumerate(heads):
            if i not in used_heads:
                target_groups.append({
                    'body': None,
                    'head': head,
                    'x': head['x'],
                    'y': head['y'],
                    'distance': head['distance_to_center'],
                    'area': head['box_area']
                })

        return target_groups

    def _match_to_tracked_targets(
            self,
            current_groups: List[Dict]
    ) -> Dict[int, Dict]:
        """
        ⭐ 新增：将当前帧的目标组匹配到历史追踪目标

        返回: {target_id: group_data}
        """
        identity_threshold = get_config('TARGET_IDENTITY_DISTANCE', 80)
        max_lost_frames = get_config('MAX_LOST_FRAMES', 30)

        # 清理过期目标
        self.tracked_targets = {
            tid: data for tid, data in self.tracked_targets.items()
            if self.current_frame - data['last_seen_frame'] < max_lost_frames
        }

        matched_targets = {}
        used_groups = set()

        # 第一轮：匹配已存在的目标
        for tid, tracked in self.tracked_targets.items():
            best_match = None
            min_distance = float('inf')

            for i, group in enumerate(current_groups):
                if i in used_groups:
                    continue

                distance = math.hypot(
                    group['x'] - tracked['x'],
                    group['y'] - tracked['y']
                )

                if distance < min_distance and distance < identity_threshold:
                    min_distance = distance
                    best_match = (i, group)

            if best_match:
                idx, group = best_match
                used_groups.add(idx)
                matched_targets[tid] = group
                # 更新追踪信息
                self.tracked_targets[tid].update({
                    'x': group['x'],
                    'y': group['y'],
                    'last_seen_frame': self.current_frame
                })

        # 第二轮：为新目标分配ID
        for i, group in enumerate(current_groups):
            if i not in used_groups:
                new_id = self.next_target_id
                self.next_target_id += 1
                matched_targets[new_id] = group
                self.tracked_targets[new_id] = {
                    'x': group['x'],
                    'y': group['y'],
                    'last_seen_frame': self.current_frame
                }

        return matched_targets

    def select_best_target(
            self,
            candidate_targets: List[Dict],
            screen_width: int,
            screen_height: int,
            reference_x: Optional[float] = None,
            reference_y: Optional[float] = None
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        ⭐ 改进版目标选择：基于持久化ID的稳定追踪
        """
        self.current_frame += 1

        # 参数准备
        max_lost_frames = get_config('MAX_LOST_FRAMES', 30)
        target_class_ids = get_config('TARGET_CLASS_IDS', [0, 1])
        switch_distance_threshold = get_config('TARGET_SWITCH_DISTANCE_THRESHOLD', 50)

        candidate_targets = [t for t in candidate_targets if t.get('class_id') in target_class_ids]

        if reference_x is None or reference_y is None:
            reference_x = screen_width // 2
            reference_y = screen_height // 2

        # 无目标处理
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

        # ⭐ 核心改进：分组 + 匹配
        current_groups = self._group_detections_by_target(
            candidate_targets, reference_x, reference_y
        )
        matched_targets = self._match_to_tracked_targets(current_groups)

        # 目标选择逻辑
        best_target_id = None
        best_group = None

        # 优先保持锁定目标
        if self.locked_target_id is not None and self.locked_target_id in matched_targets:
            locked_group = matched_targets[self.locked_target_id]

            # 检查是否有明显更优的目标
            closest_id = min(matched_targets.keys(), key=lambda tid: matched_targets[tid]['distance'])
            closest_group = matched_targets[closest_id]

            # 只有当新目标显著更近时才切换
            if closest_group['distance'] < (locked_group['distance'] - switch_distance_threshold):
                if locked_group['distance'] > 30:  # 老目标已经偏离准星
                    best_target_id = closest_id
                    best_group = closest_group
                else:
                    best_target_id = self.locked_target_id
                    best_group = locked_group
            else:
                best_target_id = self.locked_target_id
                best_group = locked_group

        # 没有锁定目标或锁定目标丢失
        if best_target_id is None:
            best_target_id = min(matched_targets.keys(), key=lambda tid: matched_targets[tid]['distance'])
            best_group = matched_targets[best_target_id]
            self.locked_target_id = best_target_id
            self.is_locked = True

        # 组内部位选择
        selected_det, part_name = self._select_part_within_group(best_group)

        # 坐标平滑
        raw_x = selected_det.get('aim_x', selected_det['x'])
        raw_y = selected_det.get('aim_y', selected_det['y'])

        is_new_target = (self.locked_target_id != best_target_id)
        smoothed_x, smoothed_y = self._apply_smoothing(raw_x, raw_y, is_new_target)
        # ⭐⭐⭐ 关键修复：更新锁定帧数 ⭐⭐⭐
        if is_new_target:
            # 切换到新目标，重置帧数
            self.target_lock_frames = 1
            self.locked_target_id = best_target_id
            self.is_locked = True
            if get_config('DEBUG_MODE', False):
                utils.log_debug(f"[目标切换] 新目标ID={best_target_id}，重置帧数")
        else:
            # 持续锁定同一目标，累积帧数
            self.target_lock_frames += 1
            if get_config('DEBUG_MODE', False) and self.target_lock_frames % 30 == 0:
                utils.log_debug(f"[目标锁定] ID={best_target_id}，已锁定{self.target_lock_frames}帧")

        self.last_target_x = max(0, min(int(smoothed_x), screen_width - 1))
        self.last_target_y = max(0, min(int(smoothed_y), screen_height - 1))
        self.frames_without_target = 0

        if get_config('DEBUG_MODE', False):
            utils.log_debug(
                f"[目标追踪] ID={best_target_id} 部位={part_name} "
                f"位置=({self.last_target_x},{self.last_target_y})"
            )

        return self.last_target_x, self.last_target_y

    def _select_part_within_group(self, group: Dict) -> Tuple[Dict, str]:
        """
        ⭐ 改进版部位选择
        """
        head = group.get('head')
        body = group.get('body')

        # 优先头部
        if get_config('ENABLE_HEAD_PRIORITY', True) and head:
            if get_config('IGNORE_SMALL_TARGET_HEAD', True):
                threshold = get_config('SMALL_TARGET_AREA_THRESHOLD', 200)
                if head['box_area'] >= threshold:
                    return head, "head"
            else:
                return head, "head"

        # 回退身体
        if body:
            return body, "body"

        # 兜底
        return head or body, "any"

    def _apply_smoothing(
            self,
            raw_x: float,
            raw_y: float,
            is_new_target: bool = False
    ) -> Tuple[int, int]:
        """平滑处理 (保持不变)"""
        if self.use_kalman:
            if is_new_target:
                self.kalman_filter.init_with_position(raw_x, raw_y)
                return int(raw_x), int(raw_y)

            smooth_x, smooth_y = self.kalman_filter.update(raw_x, raw_y)
            return int(smooth_x), int(smooth_y)
        else:
            smooth_alpha = get_config('AIM_POINT_SMOOTH_ALPHA', 0.25)
            if is_new_target or self.smoothed_aim_x is None:
                self.smoothed_aim_x = float(raw_x)
                self.smoothed_aim_y = float(raw_y)
            else:
                self.smoothed_aim_x = smooth_alpha * raw_x + (1 - smooth_alpha) * self.smoothed_aim_x
                self.smoothed_aim_y = smooth_alpha * raw_y + (1 - smooth_alpha) * self.smoothed_aim_y
            return int(self.smoothed_aim_x), int(self.smoothed_aim_y)

    def should_send_command(
            self,
            target_x: int,
            target_y: int,
            reference_x: float,
            reference_y: float
    ) -> bool:
        """判断是否需要发送移动命令 (保持不变)"""
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
        """获取预判位置 (保持不变)"""
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
        self.locked_target_id = None
        self.frames_without_target = 0
        self.target_lock_frames = 0  # ⭐ 添加这行
        self.tracked_targets.clear()

        self.smoothed_aim_x = None
        self.smoothed_aim_y = None

        if self.use_kalman:
            self.kalman_filter.reset()

        if get_config('DEBUG_MODE', False):
            utils.log_debug("[重置追踪] 所有状态已清空")
