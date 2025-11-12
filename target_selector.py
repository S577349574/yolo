# target_selector.py
"""目标选择器（增强特效干扰抵抗能力）"""

import math
import time
from typing import List, Dict, Optional, Tuple
from collections import deque

import utils
from config_manager import get_config


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

        # 原始位置（未经平滑，用于速度计算）
        self.last_raw_x: Optional[float] = None
        self.last_raw_y: Optional[float] = None

        # 速度跟踪
        self.last_target_time: float = time.time()
        self.target_velocity_x: float = 0.0
        self.target_velocity_y: float = 0.0
        self.velocity_smooth_alpha: float = get_config('VELOCITY_SMOOTH_ALPHA', 0.3)

        # 加速度跟踪
        self.last_velocity_x: float = 0.0
        self.last_velocity_y: float = 0.0
        self.target_accel_x: float = 0.0
        self.target_accel_y: float = 0.0
        self.accel_smooth_alpha: float = get_config('ACCEL_SMOOTH_ALPHA', 0.2)

        # 预测开关
        self.enable_velocity_prediction: bool = get_config('ENABLE_VELOCITY_PREDICTION', True)
        self.enable_accel_prediction: bool = get_config('ENABLE_ACCEL_PREDICTION', False)

        # 🔥 新增: 置信度历史记忆（用于抵抗特效干扰）
        self.confidence_history: deque = deque(maxlen=get_config('CONFIDENCE_HISTORY_SIZE', 10))
        self.baseline_confidence: float = 0.0  # 未受干扰时的基准置信度

        # 🔥 新增: 攻击状态保护
        self.under_attack_frames: int = 0  # 连续低置信度帧数（疑似被攻击）
        self.attack_protection_enabled: bool = False  # 攻击保护激活标志

    def calculate_aim_point(
            self,
            box: Tuple[float, float, float, float],
            capture_area: Dict[str, int]
    ) -> Tuple[int, int]:
        """✅ 动态读取配置计算瞄准点"""
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
        """✅ 动态读取平滑参数"""
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
        """🔥 新增: 更新置信度历史并检测攻击状态"""
        self.confidence_history.append(confidence)

        if len(self.confidence_history) >= 3:
            # 计算基准置信度（使用中位数，更抗噪声）
            sorted_conf = sorted(self.confidence_history)
            self.baseline_confidence = sorted_conf[len(sorted_conf) // 2]

            # 检测置信度骤降（疑似被攻击）
            conf_drop_threshold = get_config('CONFIDENCE_DROP_THRESHOLD', 0.15)
            recent_avg = sum(list(self.confidence_history)[-3:]) / 3

            if self.baseline_confidence - recent_avg > conf_drop_threshold:
                self.under_attack_frames += 1
            else:
                self.under_attack_frames = max(0, self.under_attack_frames - 1)

            # 激活攻击保护（连续3帧置信度低）
            attack_protection_frames = get_config('ATTACK_PROTECTION_TRIGGER_FRAMES', 3)
            self.attack_protection_enabled = (self.under_attack_frames >= attack_protection_frames)

    def _calculate_enhanced_score(
            self,
            target: Dict,
            ref_x: float,
            ref_y: float,
            max_distance: float,
            is_locked_target: bool
    ) -> float:
        """🔥 新增: 增强的目标评分（考虑攻击状态）"""
        distance = math.hypot(target['x'] - ref_x, target['y'] - ref_y)
        normalized_distance = distance / max_distance
        distance_score = 1.0 - normalized_distance

        conf_score = target['confidence']

        # 🔥 如果是锁定目标且处于攻击保护状态，使用基准置信度而非当前置信度
        if is_locked_target and self.attack_protection_enabled:
            conf_score = max(conf_score, self.baseline_confidence * 0.9)  # 使用90%基准值
            utils.log(f"🛡️ 攻击保护激活 | 原始conf={target['confidence']:.2f} → 修正conf={conf_score:.2f}")

        distance_weight = get_config('DISTANCE_WEIGHT', 0.8)
        composite_score = (
                distance_weight * distance_score +
                (1 - distance_weight) * conf_score
        )

        # 🔥 锁定目标额外加成（增强粘性）
        if is_locked_target:
            lock_bonus = get_config('LOCKED_TARGET_BONUS', 0.15)
            composite_score += lock_bonus

        return composite_score

    def select_best_target(
            self,
            candidate_targets: List[Dict],
            screen_width: int,
            screen_height: int
    ) -> Tuple[Optional[int], Optional[int]]:
        """✅ 修复多目标+特效干扰问题"""

        max_lost_frames = get_config('MAX_LOST_FRAMES', 30)
        target_identity_distance = get_config('TARGET_IDENTITY_DISTANCE', 100)
        min_target_lock_frames = get_config('MIN_TARGET_LOCK_FRAMES', 15)
        target_switch_threshold = get_config('TARGET_SWITCH_THRESHOLD', 0.2)

        # 无候选目标处理
        if not candidate_targets:
            self.frames_without_target += 1
            if self.frames_without_target >= max_lost_frames:
                self._reset_tracking()
            return None, None

        # 生成目标ID
        id_grid_size = 20
        for target in candidate_targets:
            target['id'] = (
                f"{int(target['x'] / id_grid_size)}_"
                f"{int(target['y'] / id_grid_size)}"
            )

        # 🔥 扩大搜索范围以应对特效导致的位置偏移
        search_multiplier = 2.0 if self.attack_protection_enabled else 1.0
        effective_identity_distance = target_identity_distance * search_multiplier

        # 检查锁定目标是否还存在
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

            # 🔥 ID匹配失败，尝试位置匹配（容错机制）
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
                    self.locked_target_id = closest_target['id']  # 更新ID
                    utils.log(f"⚠️ ID丢失，使用位置匹配恢复目标 (距离={distance:.1f}px)")

        # 计算所有目标得分
        max_distance = math.hypot(screen_width, screen_height)
        ref_x = self.last_target_x if self.last_target_x is not None else screen_width // 2
        ref_y = self.last_target_y if self.last_target_y is not None else screen_height // 2

        scored_targets = []
        for target in candidate_targets:
            is_locked = (current_locked_target is not None and
                         target['id'] == current_locked_target['id'])

            score = self._calculate_enhanced_score(
                target, ref_x, ref_y, max_distance, is_locked
            )

            distance = math.hypot(target['x'] - ref_x, target['y'] - ref_y)

            scored_targets.append({
                'target': target,
                'score': score,
                'distance': distance
            })

        scored_targets.sort(key=lambda x: x['score'], reverse=True)
        best_candidate = scored_targets[0]

        # 决定是否切换目标
        selected_target: Optional[Dict] = None
        is_new_target = False

        if current_locked_target is not None:
            locked_score = next(
                (st['score'] for st in scored_targets
                 if st['target']['id'] == self.locked_target_id),
                0.0
            )

            score_diff = best_candidate['score'] - locked_score

            # 🔥 攻击保护状态下提高切换阈值
            effective_switch_threshold = target_switch_threshold
            if self.attack_protection_enabled:
                effective_switch_threshold *= 2.0  # 双倍阈值
                utils.log(f"🛡️ 提高切换阈值: {target_switch_threshold:.2f} → {effective_switch_threshold:.2f}")

            if (self.target_lock_frames >= min_target_lock_frames and
                    score_diff > effective_switch_threshold):
                selected_target = best_candidate['target']
                self.locked_target_id = selected_target['id']
                self.target_lock_frames = 0
                is_new_target = True
                self._reset_motion_params()
                utils.log(f"切换目标 | 得分差: {score_diff:.2f}")
            else:
                selected_target = current_locked_target
                self.target_lock_frames += 1
        else:
            selected_target = best_candidate['target']
            self.locked_target_id = selected_target['id']
            self.target_lock_frames = 0
            is_new_target = True
            self._reset_motion_params()

        # 🔥 更新置信度追踪
        self._update_confidence_tracking(selected_target['confidence'])

        # 获取原始位置
        raw_x = selected_target['x']
        raw_y = selected_target['y']

        # 新目标处理
        if is_new_target:
            self.last_raw_x = raw_x
            self.last_raw_y = raw_y
            self.smoothed_aim_x = float(raw_x)
            self.smoothed_aim_y = float(raw_y)
            self.last_target_time = time.time()

            self.last_target_x = int(raw_x)
            self.last_target_y = int(raw_y)
            self.frames_without_target = 0
            self.is_locked = True

            return self.last_target_x, self.last_target_y

        # 速度计算和预测（保持原有逻辑）
        current_time = time.time()
        dt = current_time - self.last_target_time

        if dt < 0.001:
            dt = 0.016

        if self.enable_velocity_prediction and self.last_raw_x is not None:
            instant_vel_x = (raw_x - self.last_raw_x) / dt
            instant_vel_y = (raw_y - self.last_raw_y) / dt

            max_reasonable_speed = 3000
            speed = math.hypot(instant_vel_x, instant_vel_y)

            if speed > max_reasonable_speed:
                utils.log(f"⚠️ 检测到异常速度: {speed:.0f} px/s, 重置")
                self._reset_motion_params()
                instant_vel_x = 0
                instant_vel_y = 0

            alpha = self.velocity_smooth_alpha
            self.target_velocity_x = alpha * instant_vel_x + (1 - alpha) * self.target_velocity_x
            self.target_velocity_y = alpha * instant_vel_y + (1 - alpha) * self.target_velocity_y

            if self.enable_accel_prediction:
                instant_accel_x = (self.target_velocity_x - self.last_velocity_x) / dt
                instant_accel_y = (self.target_velocity_y - self.last_velocity_y) / dt

                accel_alpha = self.accel_smooth_alpha
                self.target_accel_x = accel_alpha * instant_accel_x + (1 - accel_alpha) * self.target_accel_x
                self.target_accel_y = accel_alpha * instant_accel_y + (1 - accel_alpha) * self.target_accel_y

                self.last_velocity_x = self.target_velocity_x
                self.last_velocity_y = self.target_velocity_y

        self.last_raw_x = raw_x
        self.last_raw_y = raw_y

        smoothed_x, smoothed_y = self._apply_smoothing(raw_x, raw_y, False)

        predict_delay = get_config('PREDICT_DELAY_SEC', 0.025)
        predict_x = smoothed_x
        predict_y = smoothed_y

        if self.enable_velocity_prediction:
            predict_x += self.target_velocity_x * predict_delay
            predict_y += self.target_velocity_y * predict_delay

            if self.enable_accel_prediction:
                predict_x += 0.5 * self.target_accel_x * (predict_delay ** 2)
                predict_y += 0.5 * self.target_accel_y * (predict_delay ** 2)

        predict_x = max(0, min(predict_x, screen_width - 1))
        predict_y = max(0, min(predict_y, screen_height - 1))

        self.last_target_x = int(predict_x)
        self.last_target_y = int(predict_y)
        self.last_target_time = current_time
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
        """✅ 动态读取死区配置"""
        offset_x = target_x - screen_center_x
        offset_y = target_y - screen_center_y
        offset_distance = math.hypot(offset_x, offset_y)

        precision_dead_zone = get_config('PRECISION_DEAD_ZONE', 2)
        return offset_distance >= precision_dead_zone

    def _reset_motion_params(self) -> None:
        """重置运动相关参数"""
        self.target_velocity_x = 0.0
        self.target_velocity_y = 0.0
        self.target_accel_x = 0.0
        self.target_accel_y = 0.0
        self.last_velocity_x = 0.0
        self.last_velocity_y = 0.0
        self.smoothed_aim_x = None
        self.smoothed_aim_y = None
        self.last_raw_x = None
        self.last_raw_y = None

    def _reset_tracking(self) -> None:
        """重置所有跟踪状态"""
        self.last_target_x = None
        self.last_target_y = None
        self.is_locked = False
        self.locked_target_id = None
        self.target_lock_frames = 0
        self.frames_without_target = 0
        self._reset_motion_params()
        self.last_target_time = time.time()

        # 🔥 重置攻击状态追踪
        self.confidence_history.clear()
        self.baseline_confidence = 0.0
        self.under_attack_frames = 0
        self.attack_protection_enabled = False
