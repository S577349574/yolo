import math
import time

import utils
from config_manager import get_config  # 修改：直接导入 get_config


class TargetSelector:
    def __init__(self):
        self.last_target_x = None
        self.last_target_y = None
        self.frames_without_target = 0
        self.is_locked = False

        # 目标锁定稳定性
        self.locked_target_id = None
        self.target_lock_frames = 0

        # 🆕 瞄准点平滑（仅对最终选定目标生效）
        self.smoothed_aim_x = None
        self.smoothed_aim_y = None
        self.smooth_alpha = get_config('AIM_POINT_SMOOTH_ALPHA', 0.3)  # 建议配置为 0.2-0.4

        self.last_send_time = 0
        self.send_interval_ms = get_config('MIN_SEND_INTERVAL_MS', 8)

    def calculate_aim_point(self, box, capture_area):
        """计算瞄准点（不平滑，返回原始坐标）"""
        x1, y1, x2, y2 = map(int, box)
        box_width = x2 - x1
        box_height = y2 - y1

        # 选择瞄准配置
        aim_config = None
        for config_name in ['close', 'medium', 'far']:
            config = get_config('AIM_POINTS')[config_name]
            if box_height > config['height_threshold']:
                aim_config = config
                break

        if aim_config is None:
            aim_config = get_config('AIM_POINTS')['far']

        # 计算原始瞄准点（屏幕坐标）
        center_x_cropped = int(x1 + box_width * 0.5 + aim_config['x_offset'])
        center_y_cropped = int(y1 + box_height * aim_config['y_ratio'])

        target_x = capture_area['left'] + center_x_cropped
        target_y = capture_area['top'] + center_y_cropped

        return target_x, target_y  # ⚠️ 返回未平滑的原始坐标

    def _apply_smoothing(self, raw_x, raw_y, is_new_target=False):
        """🆕 对最终选定目标应用平滑"""
        if is_new_target or self.smoothed_aim_x is None:
            # 切换目标或首次锁定：直接使用原始坐标（避免拖尾）
            self.smoothed_aim_x = float(raw_x)
            self.smoothed_aim_y = float(raw_y)
        else:
            # 指数移动平均平滑
            self.smoothed_aim_x = (
                self.smooth_alpha * raw_x +
                (1 - self.smooth_alpha) * self.smoothed_aim_x
            )
            self.smoothed_aim_y = (
                self.smooth_alpha * raw_y +
                (1 - self.smooth_alpha) * self.smoothed_aim_y
            )

        return int(self.smoothed_aim_x), int(self.smoothed_aim_y)

    def select_best_target(self, candidate_targets, screen_width, screen_height):
        """选择最佳目标并应用平滑"""
        if not candidate_targets:
            self.frames_without_target += 1
            if self.frames_without_target >= get_config('MAX_LOST_FRAMES'):
                self.last_target_x = None
                self.last_target_y = None
                self.is_locked = False
                self.locked_target_id = None
                self.target_lock_frames = 0
                # 🆕 丢失目标时重置平滑状态
                self.smoothed_aim_x = None
                self.smoothed_aim_y = None
            return None, None

        # 为候选目标生成ID
        for target in candidate_targets:
            target['id'] = f"{int(target['x'] / 20)}_{int(target['y'] / 20)}"

        # 检查锁定目标是否还存在
        current_locked_target = None
        if self.locked_target_id is not None:
            for target in candidate_targets:
                if target['id'] == self.locked_target_id:
                    if self.last_target_x is not None:
                        distance = math.sqrt(
                            (target['x'] - self.last_target_x) ** 2 +
                            (target['y'] - self.last_target_y) ** 2
                        )
                        if distance < get_config('TARGET_IDENTITY_DISTANCE'):
                            current_locked_target = target
                            break

        # 计算所有目标得分
        max_distance = math.sqrt(screen_width ** 2 + screen_height ** 2)
        scored_targets = []

        for target in candidate_targets:
            ref_x = self.last_target_x if self.last_target_x is not None else target['x']
            ref_y = self.last_target_y if self.last_target_y is not None else target['y']

            distance = math.sqrt(
                (target['x'] - ref_x) ** 2 +
                (target['y'] - ref_y) ** 2
            )
            normalized_distance = distance / max_distance
            distance_score = 1 - normalized_distance
            conf_score = target['confidence']

            composite_score = (get_config('DISTANCE_WEIGHT') * distance_score +
                               (1 - get_config('DISTANCE_WEIGHT')) * conf_score)

            scored_targets.append({
                'target': target,
                'score': composite_score,
                'distance': distance
            })

        scored_targets.sort(key=lambda x: x['score'], reverse=True)
        best_candidate = scored_targets[0]

        # 决定是否切换目标
        selected_target = None
        is_new_target = False  # 🆕 标记是否切换了目标

        if current_locked_target is not None:
            locked_score = next(
                (st['score'] for st in scored_targets if st['target']['id'] == self.locked_target_id),
                0
            )

            score_diff = best_candidate['score'] - locked_score

            if self.target_lock_frames >= get_config('MIN_TARGET_LOCK_FRAMES') and score_diff > get_config('TARGET_SWITCH_THRESHOLD'):
                selected_target = best_candidate['target']
                self.locked_target_id = selected_target['id']
                self.target_lock_frames = 0
                is_new_target = True  # 🆕 标记切换
                utils.log(f"🔄 切换目标 | 得分差: {score_diff:.2f}")
            else:
                selected_target = current_locked_target
                self.target_lock_frames += 1
        else:
            selected_target = best_candidate['target']
            self.locked_target_id = selected_target['id']
            self.target_lock_frames = 0
            is_new_target = True  # 🆕 首次锁定也标记

        # 🆕 仅对最终选定的目标应用平滑
        raw_x = selected_target['x']
        raw_y = selected_target['y']
        smoothed_x, smoothed_y = self._apply_smoothing(raw_x, raw_y, is_new_target)

        # 更新跟踪状态（使用平滑后的坐标）
        self.last_target_x = smoothed_x
        self.last_target_y = smoothed_y
        self.frames_without_target = 0
        self.is_locked = True

        return smoothed_x, smoothed_y  # ⚠️ 返回平滑后的坐标

    def should_send_command(self, target_x, target_y, screen_center_x, screen_center_y):
        """优化版"""
        offset_x = target_x - screen_center_x
        offset_y = target_y - screen_center_y
        offset_distance = math.hypot(offset_x, offset_y)  # 🆕 更快

        precision_dead_zone = get_config('PRECISION_DEAD_ZONE', 20)
        if offset_distance < precision_dead_zone:
            return False

        # 🆕 频率限制优化（减少时间获取次数）
        current_time = time.perf_counter() * 1000  # 🆕 更高精度
        if current_time - self.last_send_time < self.send_interval_ms:
            return False

        self.last_send_time = current_time
        return True

