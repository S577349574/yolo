# target_selector.py
"""目标选择器（支持动态配置、性能优化）"""

import math
import time
from typing import List, Dict, Optional, Tuple

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

    def calculate_aim_point(
            self,
            box: Tuple[float, float, float, float],
            capture_area: Dict[str, int]
    ) -> Tuple[int, int]:
        """✅ 动态读取配置计算瞄准点"""
        x1, y1, x2, y2 = map(int, box)
        box_width = x2 - x1
        box_height = y2 - y1

        # ✅ 每次都从配置读取（支持热更新）
        y_ratio = get_config('AIM_Y_RATIO', 0.5)
        x_offset = get_config('AIM_X_OFFSET', 0)

        # 计算瞄准点
        center_x_cropped = int(x1 + box_width * 0.5 + x_offset)
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

    def select_best_target(
            self,
            candidate_targets: List[Dict],
            screen_width: int,
            screen_height: int
    ) -> Tuple[Optional[int], Optional[int]]:
        """✅ 完全动态配置的目标选择"""

        # ✅ 动态读取所有配置参数
        max_lost_frames = get_config('MAX_LOST_FRAMES', 30)
        target_identity_distance = get_config('TARGET_IDENTITY_DISTANCE', 100)
        distance_weight = get_config('DISTANCE_WEIGHT', 0.8)
        min_target_lock_frames = get_config('MIN_TARGET_LOCK_FRAMES', 15)
        target_switch_threshold = get_config('TARGET_SWITCH_THRESHOLD', 0.2)

        # 无候选目标处理
        if not candidate_targets:
            self.frames_without_target += 1
            if self.frames_without_target >= max_lost_frames:
                self._reset_tracking()
            return None, None

        # 为候选目标生成ID（基于位置网格）
        id_grid_size = 20
        for target in candidate_targets:
            target['id'] = (
                f"{int(target['x'] / id_grid_size)}_"
                f"{int(target['y'] / id_grid_size)}"
            )

        # 检查锁定目标是否还存在
        current_locked_target: Optional[Dict] = None
        if self.locked_target_id is not None and self.last_target_x is not None:
            for target in candidate_targets:
                if target['id'] == self.locked_target_id:
                    distance = math.hypot(
                        target['x'] - self.last_target_x,
                        target['y'] - self.last_target_y
                    )
                    if distance < target_identity_distance:
                        current_locked_target = target
                        break

        # ✅ 性能优化：预计算最大距离
        max_distance = math.hypot(screen_width, screen_height)

        # 计算所有目标得分
        scored_targets = []
        ref_x = self.last_target_x if self.last_target_x is not None else screen_width // 2
        ref_y = self.last_target_y if self.last_target_y is not None else screen_height // 2

        for target in candidate_targets:
            distance = math.hypot(
                target['x'] - ref_x,
                target['y'] - ref_y
            )
            normalized_distance = distance / max_distance
            distance_score = 1.0 - normalized_distance
            conf_score = target['confidence']

            composite_score = (
                    distance_weight * distance_score +
                    (1 - distance_weight) * conf_score
            )

            scored_targets.append({
                'target': target,
                'score': composite_score,
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

            # ✅ 目标切换逻辑（使用动态阈值）
            if (self.target_lock_frames >= min_target_lock_frames and
                    score_diff > target_switch_threshold):
                selected_target = best_candidate['target']
                self.locked_target_id = selected_target['id']
                self.target_lock_frames = 0
                is_new_target = True
                utils.log(f"🔄 切换目标 | 得分差: {score_diff:.2f}")
            else:
                selected_target = current_locked_target
                self.target_lock_frames += 1
        else:
            selected_target = best_candidate['target']
            self.locked_target_id = selected_target['id']
            self.target_lock_frames = 0
            is_new_target = True

        # 应用平滑
        raw_x = selected_target['x']
        raw_y = selected_target['y']
        smoothed_x, smoothed_y = self._apply_smoothing(raw_x, raw_y, is_new_target)

        # 更新状态
        self.last_target_x = smoothed_x
        self.last_target_y = smoothed_y
        self.frames_without_target = 0
        self.is_locked = True

        return smoothed_x, smoothed_y

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

    def _reset_tracking(self) -> None:
        """重置所有跟踪状态"""
        self.last_target_x = None
        self.last_target_y = None
        self.is_locked = False
        self.locked_target_id = None
        self.target_lock_frames = 0
        self.smoothed_aim_x = None
        self.smoothed_aim_y = None
