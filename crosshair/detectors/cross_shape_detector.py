# crosshair/detectors/cross_shape_detector.py
"""
十字形状准星检测器
"""
import cv2
import numpy as np
from typing import Optional, Tuple
from ..base import CrosshairDetector
from config.config_manager import get_config
import utils


class CrossShapeDetector(CrosshairDetector):
    """检测十字形准星"""

    def __init__(self):
        super().__init__()
        self.min_line_length = get_config('CROSSHAIR_MIN_LINE_LENGTH', 5)
        self.max_line_gap = get_config('CROSSHAIR_MAX_LINE_GAP', 2)
        self.angle_tolerance = get_config('CROSSHAIR_ANGLE_TOLERANCE', 10)

        utils.log(f"✚ {self.get_name()}")

    def get_name(self) -> str:
        return "十字形状检测器"

    def _detect_impl(self, roi: np.ndarray) -> Optional[Tuple[int, int]]:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, 10,
            minLineLength=self.min_line_length,
            maxLineGap=self.max_line_gap
        )

        if lines is None or len(lines) < 2:
            return None

        h_lines, v_lines = [], []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)

            if angle < self.angle_tolerance or angle > 180 - self.angle_tolerance:
                h_lines.append(line[0])
            elif 90 - self.angle_tolerance < angle < 90 + self.angle_tolerance:
                v_lines.append(line[0])

        if not h_lines or not v_lines:
            return None

        h_center = np.mean([[(x1 + x2) / 2, (y1 + y2) / 2] for x1, y1, x2, y2 in h_lines], axis=0)
        v_center = np.mean([[(x1 + x2) / 2, (y1 + y2) / 2] for x1, y1, x2, y2 in v_lines], axis=0)

        cx = int((h_center[0] + v_center[0]) / 2)
        cy = int((h_center[1] + v_center[1]) / 2)

        return (cx, cy)
