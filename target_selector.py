import math
import numpy as np
from collections import deque
from typing import List, Dict, Optional, Tuple

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

    def update_noise(self, measurement_noise: float):
        """动态更新观测噪声"""
        self.R = np.eye(2, dtype=np.float32) * measurement_noise


class TargetSelector:
    def __init__(self):
        self.last_target_x: Optional[int] = None
        self.last_target_y: Optional[int] = None
        self.frames_without_target: int = 0
        self.is_locked: bool = False

        # 目标锁定稳定性
        self.locked_target_id: Optional[str] = None
        self.target_lock_frames: int = 0

        # 瞄准点平滑
        self.smoothed_aim_x: Optional[float] = None
        self.smoothed_aim_y: Optional[float] = None

        self.last_send_time: float = 0

        # 置信度历史记忆（用于抵抗特效干扰）
        self.confidence_history: deque = deque(maxlen=get_config('CONFIDENCE_HISTORY_SIZE', 10))
        self.baseline_confidence: float = 0.0

        # 攻击状态保护
        self.under_attack_frames: int = 0
        self.attack_protection_enabled: bool = False

        # 战斗保护模式
        self.combat_mode_threshold = get_config('COMBAT_MODE_THRESHOLD', 10)
        self.in_combat_mode = False
        self.lock_initial_confidence = 0.0

        # ⭐ 卡尔曼滤波器
        self.kalman_filter = TargetKalmanFilter(
            process_noise=get_config('KALMAN_PROCESS_NOISE', 0.1),
            measurement_noise=get_config('KALMAN_MEASUREMENT_NOISE', 5.0)
        )

        # 是否启用卡尔曼滤波
        self.use_kalman = get_config('USE_KALMAN_FILTER', True)

    def calculate_aim_point(
            self,
            box: Tuple[float, float, float, float],
            capture_area: Dict[str, int]
    ) -> Tuple[int, int]:
        x1, y1, x2, y2 = map(int, box)
        box_width = x2 - x1
        box_height = y2 - y1

        y_ratio = get_config('AIM_Y_RATIO', 0.5)
        x_offset = get_config('AIM_X_OFFSET', 0)

        center_x_cropped = int(x1 + box_width * x_offset)
        center_y_cropped = int(y1 + box_height * y_ratio)

        target_x = capture_area['left'] + center_x_cropped
        target_y = capture_area['top'] + center_y_cropped

        return target_x, target_y

    def _apply_smoothing(
            self,
            raw_x: float,
            raw_y: float,
            is_new_target: bool = False
    ) -> Tuple[int, int]:
        """平滑处理 - 支持 EMA 或卡尔曼"""

        if self.use_kalman:
            # ⭐ 卡尔曼滤波路径
            if is_new_target:
                self.kalman_filter.init_with_position(raw_x, raw_y)
                return int(raw_x), int(raw_y)

            smooth_x, smooth_y = self.kalman_filter.update(raw_x, raw_y)

            delta_x = abs(smooth_x - raw_x)
            delta_y = abs(smooth_y - raw_y)
            if delta_x > 5 or delta_y > 5:
                utils.log(f"[Kalman] 原始({raw_x:.0f},{raw_y:.0f}) → 平滑({smooth_x:.0f},{smooth_y:.0f})")

            return int(smooth_x), int(smooth_y)

        else:
            # 原有 EMA 路径
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

    def _update_confidence_tracking(self, confidence: float) -> None:
        self.confidence_history.append(confidence)

        if len(self.confidence_history) >= 3:
            sorted_conf = sorted(self.confidence_history)
            self.baseline_confidence = sorted_conf[len(sorted_conf) // 2]

            conf_drop_threshold = get_config('CONFIDENCE_DROP_THRESHOLD', 0.15)
            recent_avg = sum(list(self.confidence_history)[-3:]) / 3

            if self.baseline_confidence - recent_avg > conf_drop_threshold:
                self.under_attack_frames += 1
            else:
                self.under_attack_frames = max(0, self.under_attack_frames - 1)

            attack_protection_frames = get_config('ATTACK_PROTECTION_TRIGGER_FRAMES', 3)
            self.attack_protection_enabled = (
                    self.under_attack_frames >= attack_protection_frames
            )

            # ⭐ 被攻击时动态调整卡尔曼观测噪声
            if self.use_kalman:
                if self.attack_protection_enabled:
                    # 置信度骤降，更相信预测而非观测
                    self.kalman_filter.update_noise(15.0)
                else:
                    # 正常情况
                    self.kalman_filter.update_noise(
                        get_config('KALMAN_MEASUREMENT_NOISE', 5.0)
                    )

    def _calculate_enhanced_score(
            self,
            target: Dict,
            ref_x: float,
            ref_y: float,
            max_distance: float,
            is_locked_target: bool
    ) -> float:
        distance = math.hypot(target['x'] - ref_x, target['y'] - ref_y)
        normalized_distance = distance / max_distance
        distance_score = 1.0 - normalized_distance

        conf_score = target['confidence']

        if is_locked_target and self.in_combat_mode:
            baseline_ratio = get_config('CONFIDENCE_BASELINE_RATIO', 0.95)
            conf_score = max(conf_score, self.lock_initial_confidence * baseline_ratio)

            distance_boost = get_config('COMBAT_MODE_DISTANCE_BOOST', 7.0)
            distance_score = min(1.0, distance_score * distance_boost)

            if conf_score > target['confidence'] and self.target_lock_frames < 30:
                utils.log(
                    f" 修正置信度 | "
                    f"{target['confidence']:.2f}→{conf_score:.2f}"
                )

        elif is_locked_target and self.attack_protection_enabled:
            baseline_ratio = get_config('CONFIDENCE_BASELINE_RATIO', 0.95)
            conf_score = max(conf_score, self.baseline_confidence * baseline_ratio)
            distance_boost = get_config('ATTACK_PROTECTION_DISTANCE_BOOST', 1.5)
            distance_score = min(1.0, distance_score * distance_boost)

        distance_weight = get_config('DISTANCE_WEIGHT', 0.8)
        composite_score = (
                distance_weight * distance_score +
                (1 - distance_weight) * conf_score
        )

        if is_locked_target:
            if self.in_combat_mode:
                lock_bonus = get_config('COMBAT_MODE_LOCK_BONUS', 0.60)
            else:
                lock_bonus = get_config('LOCKED_TARGET_BONUS', 0.35)
            composite_score += lock_bonus

        return composite_score

    def select_best_target(
            self,
            candidate_targets: List[Dict],
            screen_width: int,
            screen_height: int
    ) -> Tuple[Optional[int], Optional[int]]:

        max_lost_frames = get_config('MAX_LOST_FRAMES', 30)
        target_identity_distance = get_config('TARGET_IDENTITY_DISTANCE', 100)
        min_target_lock_frames = get_config('MIN_TARGET_LOCK_FRAMES', 15)
        target_switch_threshold = get_config('TARGET_SWITCH_THRESHOLD', 0.1)

        # ⭐ 无目标时使用卡尔曼预测
        if not candidate_targets:
            self.frames_without_target += 1

            if self.frames_without_target >= max_lost_frames:
                self._reset_tracking()
                return None, None

            # ⭐ 尝试用卡尔曼预测填充
            if self.use_kalman and self.is_locked:
                predicted = self.kalman_filter.predict_only(
                    max_frames=get_config('KALMAN_MAX_PREDICT_FRAMES', 5)
                )

                if predicted is not None:
                    pred_x, pred_y = predicted

                    # 边界检查
                    pred_x = max(0, min(int(pred_x), screen_width - 1))
                    pred_y = max(0, min(int(pred_y), screen_height - 1))

                    self.last_target_x = pred_x
                    self.last_target_y = pred_y

                    return pred_x, pred_y

            return None, None

        id_grid_size = 20
        for target in candidate_targets:
            target['id'] = (
                f"{int(target['x'] / id_grid_size)}_"
                f"{int(target['y'] / id_grid_size)}"
            )

        search_multiplier = 2.0 if (self.attack_protection_enabled or self.in_combat_mode) else 1.0
        effective_identity_distance = target_identity_distance * search_multiplier

        current_locked_target: Optional[Dict] = None
        if self.locked_target_id is not None and self.last_target_x is not None:
            for target in candidate_targets:
                if target['id'] == self.locked_target_id:
                    distance = math.hypot(
                        target['x'] - self.last_target_x,
                        target['y'] - self.last_target_y
                    )
                    if distance < effective_identity_distance:
                        current_locked_target = target
                        break

            if current_locked_target is None:
                closest_target = min(
                    candidate_targets,
                    key=lambda t: math.hypot(
                        t['x'] - self.last_target_x,
                        t['y'] - self.last_target_y
                    )
                )
                distance = math.hypot(
                    closest_target['x'] - self.last_target_x,
                    closest_target['y'] - self.last_target_y
                )
                if distance < effective_identity_distance:
                    current_locked_target = closest_target
                    self.locked_target_id = closest_target['id']

        max_distance = math.hypot(screen_width, screen_height)
        ref_x = self.last_target_x if self.last_target_x is not None else screen_width // 2
        ref_y = self.last_target_y if self.last_target_y is not None else screen_height // 2

        scored_targets = []
        for idx, target in enumerate(candidate_targets):
            is_locked = (current_locked_target is not None and
                         target['id'] == current_locked_target['id'])

            score = self._calculate_enhanced_score(
                target, ref_x, ref_y, max_distance, is_locked
            )

            distance = math.hypot(target['x'] - ref_x, target['y'] - ref_y)

            scored_targets.append({
                'target': target,
                'score': score,
                'distance': distance,
                'index': idx
            })

        scored_targets.sort(key=lambda x: x['score'], reverse=True)
        best_candidate = scored_targets[0]

        is_new_target = False

        if current_locked_target is not None:
            if self.target_lock_frames >= self.combat_mode_threshold:
                if not self.in_combat_mode:
                    self.in_combat_mode = True
                    utils.log(f" 进入战斗模式 (已锁定{self.target_lock_frames}帧)")

            locked_score = next(
                (st['score'] for st in scored_targets
                 if st['target']['id'] == self.locked_target_id),
                0.0
            )

            score_diff = best_candidate['score'] - locked_score

            effective_switch_threshold = target_switch_threshold
            if self.in_combat_mode:
                effective_switch_threshold *= 3.0
            elif self.attack_protection_enabled:
                effective_switch_threshold *= 2.0

            if (self.target_lock_frames >= min_target_lock_frames and
                    score_diff > effective_switch_threshold):
                selected_target = best_candidate['target']
                self.locked_target_id = selected_target['id']
                self.target_lock_frames = 0
                is_new_target = True
                self.in_combat_mode = False
                self._reset_motion_params()
                utils.log(
                    f"切换目标 | "
                    f"得分差:{score_diff:.2f} > 阈值:{effective_switch_threshold:.2f}"
                )
            else:
                selected_target = current_locked_target
                self.target_lock_frames += 1
        else:
            selected_target = best_candidate['target']
            self.locked_target_id = selected_target['id']
            self.target_lock_frames = 0
            is_new_target = True
            self.in_combat_mode = False
            self._reset_motion_params()

        if is_new_target:
            self.lock_initial_confidence = selected_target['confidence']

            other_targets_info = []
            for st in scored_targets:
                if st['target']['id'] != self.locked_target_id:
                    other_targets_info.append(
                        f"T{st['index']}({st['target']['confidence']:.2f})"
                    )

            other_targets_str = " | ".join(other_targets_info) if other_targets_info else "无"

            utils.log(
                f"  锁定新目标 | "
                f"T{best_candidate['index']}({self.lock_initial_confidence:.2f}) | "
                f"其他目标: {other_targets_str}"
            )

        self._update_confidence_tracking(selected_target['confidence'])

        raw_x = selected_target['x']
        raw_y = selected_target['y']

        if is_new_target:
            self.smoothed_aim_x = float(raw_x)
            self.smoothed_aim_y = float(raw_y)

            self.last_target_x = int(raw_x)
            self.last_target_y = int(raw_y)
            self.frames_without_target = 0
            self.is_locked = True

            return self.last_target_x, self.last_target_y

        smoothed_x, smoothed_y = self._apply_smoothing(raw_x, raw_y, False)

        smoothed_x = max(0, min(smoothed_x, screen_width - 1))
        smoothed_y = max(0, min(smoothed_y, screen_height - 1))

        self.last_target_x = int(smoothed_x)
        self.last_target_y = int(smoothed_y)
        self.frames_without_target = 0
        self.is_locked = True

        return self.last_target_x, self.last_target_y

    def should_send_command(
            self,
            target_x: int,
            target_y: int,
            screen_center_x: int,
            screen_center_y: int
    ) -> bool:
        offset_x = target_x - screen_center_x
        offset_y = target_y - screen_center_y
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

    def _reset_motion_params(self) -> None:
        """重置运动相关参数"""
        self.smoothed_aim_x = None
        self.smoothed_aim_y = None

        # ⭐ 重置卡尔曼
        if self.use_kalman:
            self.kalman_filter.reset()

    def _reset_tracking(self) -> None:
        """重置所有跟踪状态"""
        self.last_target_x = None
        self.last_target_y = None
        self.is_locked = False
        self.locked_target_id = None
        self.target_lock_frames = 0
        self.frames_without_target = 0
        self._reset_motion_params()

        self.confidence_history.clear()
        self.baseline_confidence = 0.0
        self.under_attack_frames = 0
        self.attack_protection_enabled = False

        self.in_combat_mode = False
        self.lock_initial_confidence = 0.0

        # ⭐ 重置卡尔曼
        if self.use_kalman:
            self.kalman_filter.reset()
