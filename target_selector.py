"""目标选择与瞄准点计算（后坐力补偿版）"""
import math
import time
import win32api
from config import *


class TargetSelector:
    def __init__(self):
        self.last_target_x = None
        self.last_target_y = None
        self.frames_without_target = 0
        self.is_locked = False
        self.last_command_x = None
        self.last_command_y = None
        self.last_send_time = 0
        self.is_arrived = False
        self.consecutive_arrived_frames = 0

        # 稳定性控制
        self.stable_frames_count = 0
        self.arrival_time = 0
        self.in_cooldown = False

        # 目标锁定稳定性
        self.locked_target_id = None
        self.target_lock_frames = 0
        self.min_lock_frames = MIN_TARGET_LOCK_FRAMES
        self.target_switch_threshold = TARGET_SWITCH_THRESHOLD

        # 🆕 后坐力检测
        self.last_mouse_y = None
        self.recoil_detected = False
        self.recoil_history = []  # 用于平滑检测
        self.recoil_history_size = 3

    def calculate_aim_point(self, box, capture_area):
        """根据目标大小动态计算精准瞄准点"""
        x1, y1, x2, y2 = map(int, box)
        box_width = x2 - x1
        box_height = y2 - y1

        aim_config = None
        for config_name in ['close', 'medium', 'far']:
            config = AIM_POINTS[config_name]
            if box_height > config['height_threshold']:
                aim_config = config
                break

        if aim_config is None:
            aim_config = AIM_POINTS['far']

        center_x_cropped = int(x1 + box_width * 0.5 + aim_config['x_offset'])
        center_y_cropped = int(y1 + box_height * aim_config['y_ratio'])

        target_screen_x = capture_area['left'] + center_x_cropped
        target_screen_y = capture_area['top'] + center_y_cropped

        return target_screen_x, target_screen_y

    def detect_recoil(self, current_mouse_y):
        """
        检测是否正在经历后坐力

        返回:
            bool: True表示检测到后坐力
        """
        # 检查是否启用后坐力补偿
        recoil_mode_enabled = globals().get('RECOIL_COMPENSATION_MODE', False)
        if not recoil_mode_enabled:
            return False

        if self.last_mouse_y is None:
            self.last_mouse_y = current_mouse_y
            return False

        # 计算Y轴移动（正值=向上移动=后坐力）
        vertical_movement = self.last_mouse_y - current_mouse_y
        self.last_mouse_y = current_mouse_y

        # 添加到历史记录
        self.recoil_history.append(vertical_movement)
        if len(self.recoil_history) > self.recoil_history_size:
            self.recoil_history.pop(0)

        # 获取阈值（从config或使用默认值）
        threshold = globals().get('RECOIL_DETECTION_THRESHOLD', 15)

        # 判断后坐力：单帧超阈值 或 连续向上移动
        instant_recoil = vertical_movement > threshold
        sustained_recoil = (
            len(self.recoil_history) >= 2 and
            all(v > 5 for v in self.recoil_history[-2:])
        )

        if instant_recoil or sustained_recoil:
            self.recoil_detected = True
            print(f"🔥 检测到后坐力 | 垂直位移: {vertical_movement:.1f}px | 模式: {'瞬时' if instant_recoil else '持续'}")
            return True
        else:
            # 逐渐衰减后坐力状态
            if self.recoil_detected and vertical_movement < -5:
                self.recoil_detected = False
            return False

    def select_best_target(self, candidate_targets, screen_width, screen_height):
        """
        选择最佳目标（防切换版）

        核心改进：
        1. 为每个目标生成稳定的ID
        2. 优先保持当前锁定目标
        3. 只有在明显更优时才切换
        """
        if not candidate_targets:
            self.frames_without_target += 1
            if self.frames_without_target >= MAX_LOST_FRAMES:
                self.last_target_x = None
                self.last_target_y = None
                self.is_locked = False
                self.is_arrived = False
                self.consecutive_arrived_frames = 0
                self.stable_frames_count = 0
                self.in_cooldown = False
                self.locked_target_id = None
                self.target_lock_frames = 0
            return None, None

        # 为候选目标生成稳定ID（基于位置）
        for target in candidate_targets:
            target['id'] = f"{int(target['x'] / 20)}_{int(target['y'] / 20)}"

        # 如果有锁定的目标，先检查它是否还存在
        current_locked_target = None
        if self.locked_target_id is not None:
            for target in candidate_targets:
                if target['id'] == self.locked_target_id:
                    if self.last_target_x is not None:
                        distance = math.sqrt(
                            (target['x'] - self.last_target_x) ** 2 +
                            (target['y'] - self.last_target_y) ** 2
                        )
                        if distance < 100:
                            current_locked_target = target
                            break

        # 计算所有目标的得分
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

            composite_score = (DISTANCE_WEIGHT * distance_score +
                               (1 - DISTANCE_WEIGHT) * conf_score)

            scored_targets.append({
                'target': target,
                'score': composite_score,
                'distance': distance
            })

        # 按得分排序
        scored_targets.sort(key=lambda x: x['score'], reverse=True)
        best_candidate = scored_targets[0]

        # 决定是否切换目标
        selected_target = None

        if current_locked_target is not None:
            locked_score = next(
                (st['score'] for st in scored_targets if st['target']['id'] == self.locked_target_id),
                0
            )

            score_diff = best_candidate['score'] - locked_score

            if self.target_lock_frames >= self.min_lock_frames and score_diff > self.target_switch_threshold:
                selected_target = best_candidate['target']
                self.locked_target_id = selected_target['id']
                self.target_lock_frames = 0
                print(f"🔄 切换目标 | 得分差: {score_diff:.2f} | 新目标位置: ({selected_target['x']}, {selected_target['y']})")
            else:
                selected_target = current_locked_target
                self.target_lock_frames += 1
        else:
            selected_target = best_candidate['target']
            self.locked_target_id = selected_target['id']
            self.target_lock_frames = 0

        # 更新状态
        self.last_target_x = selected_target['x']
        self.last_target_y = selected_target['y']
        self.frames_without_target = 0
        self.is_locked = True

        return selected_target['x'], selected_target['y']

    def should_send_command(self, target_x, target_y):
        """
        判断是否需要发送鼠标指令（后坐力补偿版）

        核心改进：
        1. 检测后坐力并自动提高响应速度
        2. 后坐力时立即取消"已到达"状态
        3. 动态调整发送频率
        """
        if not ENABLE_SMART_THRESHOLD:
            return True

        current_time = time.time() * 1000
        current_mouse_x, current_mouse_y = win32api.GetCursorPos()

        # 🆕 检测后坐力
        is_recoiling = self.detect_recoil(current_mouse_y)

        mouse_to_target_distance = math.sqrt(
            (target_x - current_mouse_x) ** 2 +
            (target_y - current_mouse_y) ** 2
        )

        # 🆕 后坐力时的特殊处理
        if is_recoiling:
            # 立即取消已到达状态和冷却
            if self.is_arrived or self.in_cooldown:
                print(f"⚡ 后坐力触发，强制重新瞄准 | 距离: {mouse_to_target_distance:.1f}px")

            self.is_arrived = False
            self.in_cooldown = False
            self.stable_frames_count = 0
            self.consecutive_arrived_frames = 0

            # 强制发送指令（忽略频率限制）
            self.last_command_x = target_x
            self.last_command_y = target_y
            self.last_send_time = current_time
            return True

        # 冷却期检查
        if self.in_cooldown:
            elapsed = current_time - self.arrival_time
            if elapsed < COOLDOWN_AFTER_ARRIVAL_MS:
                if mouse_to_target_distance > ARRIVAL_THRESHOLD_EXIT:
                    self.in_cooldown = False
                    self.is_arrived = False
                    self.stable_frames_count = 0
                    print(f"⚠️ 冷却期结束，目标远离 | 距离: {mouse_to_target_distance:.1f}px")
                else:
                    return False
            else:
                self.in_cooldown = False

        # 稳定帧判断
        if mouse_to_target_distance < ARRIVAL_THRESHOLD_ENTER:
            self.stable_frames_count += 1

            if self.stable_frames_count >= STABLE_FRAMES_REQUIRED:
                if not self.is_arrived:
                    self.is_arrived = True
                    self.arrival_time = current_time
                    self.in_cooldown = True
                    print(f"🎯 已到达目标（稳定{self.stable_frames_count}帧）| 距离: {mouse_to_target_distance:.1f}px")

                self.consecutive_arrived_frames += 1
                return False
            else:
                return False
        else:
            if self.stable_frames_count > 0:
                self.stable_frames_count = 0

        # 滞后机制
        if self.is_arrived:
            if mouse_to_target_distance > ARRIVAL_THRESHOLD_EXIT:
                self.is_arrived = False
                self.consecutive_arrived_frames = 0
                self.stable_frames_count = 0
                self.in_cooldown = False
                print(f"⚠️ 目标远离，重新瞄准 | 距离: {mouse_to_target_distance:.1f}px")
            else:
                if self.last_command_x is not None:
                    command_dx = abs(target_x - self.last_command_x)
                    command_dy = abs(target_y - self.last_command_y)
                    command_drift = math.sqrt(command_dx ** 2 + command_dy ** 2)

                    x_drift_priority = command_dx > command_dy * 2 and command_dx > 2

                    if command_drift > 3 or x_drift_priority:
                        self.last_command_x = target_x
                        self.last_command_y = target_y
                        print(f"🔧 滞后微调 | drift: {command_drift:.1f}px | dx: {command_dx:.1f}px")
                        return True

                return False

        # 🆕 后坐力补偿模式下的动态频率限制
        interval_limit = MIN_SEND_INTERVAL_MS
        if self.recoil_detected:
            multiplier = globals().get('RECOIL_RESPONSE_MULTIPLIER', 2.0)
            interval_limit = MIN_SEND_INTERVAL_MS / multiplier

        if current_time - self.last_send_time < interval_limit:
            return False

        # 首次锁定
        if not self.is_locked or self.last_command_x is None:
            if mouse_to_target_distance > INITIAL_LOCK_THRESHOLD:
                self.last_command_x = target_x
                self.last_command_y = target_y
                self.last_send_time = current_time
                return True
            return False

        # 判断目标移动
        target_movement = math.sqrt(
            (target_x - self.last_command_x) ** 2 +
            (target_y - self.last_command_y) ** 2
        )

        dx = abs(target_x - current_mouse_x)
        dy = abs(target_y - current_mouse_y)

        # 🆕 后坐力时使用更敏感的阈值
        if self.recoil_detected:
            dynamic_dist_threshold = 2  # 后坐力时极敏感
        else:
            dynamic_dist_threshold = 3 if mouse_to_target_distance < 10 else 5

        x_priority = dx > dy * 2 and dx > dynamic_dist_threshold

        should_send = (
                target_movement > MOVEMENT_THRESHOLD_PIXELS or
                mouse_to_target_distance > dynamic_dist_threshold or
                x_priority
        )

        if should_send:
            self.last_command_x = target_x
            self.last_command_y = target_y
            self.last_send_time = current_time

            # 调试输出（可选）
            if self.recoil_detected:
                print(f"🔥 后坐力补偿 | 距离: {mouse_to_target_distance:.1f}px | dx: {dx:.1f}px")
            # else:
            #     print(f"📡 发送指令 | 距离: {mouse_to_target_distance:.1f}px | dx: {dx:.1f}px")

        return should_send
