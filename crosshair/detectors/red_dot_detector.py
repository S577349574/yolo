# crosshair/detectors/red_dot_detector.py
"""
简化版红点准星检测器 v5.5 - 生产版
"""

from typing import Optional, Tuple
import cv2
import numpy as np
import utils
from crosshair import CrosshairDetector


class SimpleRedDotDetector(CrosshairDetector):
    """简化红点检测器（红色+亮度中心，抗光照变化）"""

    def __init__(self):
        super().__init__()

        # 颜色范围
        self.red_lower1 = np.array([0, 100, 80])
        self.red_upper1 = np.array([10, 255, 255])
        self.red_lower2 = np.array([170, 100, 80])
        self.red_upper2 = np.array([180, 255, 255])

        # 尺寸参数
        self.min_red_area = 10
        self.max_red_area = 200

        # 中心亮度验证
        self.min_center_brightness = 100

        utils.log(f"🔴 {self.get_name()} 初始化完成")

    def get_name(self) -> str:
        return "简化红点检测器 v5.5"

    def _detect_impl(self, roi: np.ndarray) -> Optional[Tuple[int, int]]:
        """检测红点准星位置"""
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        h, w = roi.shape[:2]
        roi_center_x, roi_center_y = w // 2, h // 2

        # 创建红色掩码
        red_mask1 = cv2.inRange(hsv, self.red_lower1, self.red_upper1)
        red_mask2 = cv2.inRange(hsv, self.red_lower2, self.red_upper2)
        red_mask = cv2.bitwise_or(red_mask1, red_mask2)

        # 形态学处理
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)

        if np.sum(red_mask > 0) == 0:
            return None

        # 查找红色轮廓
        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if len(contours) == 0:
            return None

        # 遍历轮廓，找最佳候选
        candidates = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_red_area or area > self.max_red_area:
                continue

            # 在轮廓内找最亮点
            contour_mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.drawContours(contour_mask, [contour], -1, 255, -1)

            max_brightness = np.max(gray[contour_mask > 0])
            brightest_points = np.where((gray == max_brightness) & (contour_mask > 0))

            if len(brightest_points[0]) == 0:
                continue

            cy = np.mean(brightest_points[0])
            cx = np.mean(brightest_points[1])

            # 亮度验证
            if max_brightness < self.min_center_brightness:
                continue

            # 综合评分
            distance = np.hypot(cx - roi_center_x, cy - roi_center_y)
            brightness_score = max_brightness / 255
            area_score = min(1.0, area / 50)
            distance_score = max(0, 1 - distance / 50)

            final_score = (brightness_score * 0.4 +
                           area_score * 0.3 +
                           distance_score * 0.3)

            candidates.append((final_score, (cx, cy), distance))

        # 选择最佳候选
        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        _, best_pos, distance_to_center = candidates[0]

        # 亚像素级中心对齐
        if distance_to_center < 1.5:
            return roi_center_x, roi_center_y

        return best_pos
