# crosshair/detectors/color_detector.py
"""
颜色匹配准星检测器
"""
import cv2
import numpy as np
from typing import Optional, Tuple
from ..base import CrosshairDetector
from config.config_manager import get_config
import utils


class ColorCrosshairDetector(CrosshairDetector):
    """基于颜色的准星检测（适合纯色准星）"""

    def __init__(self):
        super().__init__()
        self.target_color = np.array(
            get_config('CROSSHAIR_COLOR', [0, 255, 0]),
            dtype=np.uint8
        )
        self.tolerance = get_config('CROSSHAIR_COLOR_TOLERANCE', 30)
        self.min_pixels = get_config('CROSSHAIR_MIN_PIXELS', 5)

        utils.log(f"🎨 {self.get_name()}:")
        utils.log(f"   目标颜色(BGR): {self.target_color.tolist()}")
        utils.log(f"   容差: ±{self.tolerance}")

    def get_name(self) -> str:
        return "颜色准星检测器"

    def _detect_impl(self, roi: np.ndarray) -> Optional[Tuple[int, int]]:
        tc = self.target_color.astype(np.int16)
        lower = np.clip(tc - self.tolerance, 0, 255).astype(np.uint8)
        upper = np.clip(tc + self.tolerance, 0, 255).astype(np.uint8)

        mask = cv2.inRange(roi, lower, upper)
        coords = cv2.findNonZero(mask)

        if coords is None or len(coords) < self.min_pixels:
            return None

        M = cv2.moments(mask)
        if M['m00'] == 0:
            return None

        cx = int(M['m10'] / M['m00'])
        cy = int(M['m01'] / M['m00'])

        return cx, cy
