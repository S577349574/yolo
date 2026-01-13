# crosshair/base.py
"""
准星检测器抽象基类
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import numpy as np
from config_manager import get_config


class CrosshairDetector(ABC):
    """准星检测器抽象基类"""

    def __init__(self):
        self.enabled = get_config('ENABLE_CROSSHAIR_DETECTION', False)
        self.search_radius = get_config('CROSSHAIR_SEARCH_RADIUS', 80)
        self.smooth_factor = get_config('CROSSHAIR_SMOOTH_FACTOR', 0.3)

        # 缓存上次位置
        self.last_pos: Optional[Tuple[int, int]] = None
        self.last_valid_count = 0
        self.max_lost_frames = get_config('CROSSHAIR_MAX_LOST_FRAMES', 5)

    @abstractmethod
    def _detect_impl(self, roi: np.ndarray) -> Optional[Tuple[int, int]]:
        """
        子类实现的核心检测逻辑

        Args:
            roi: 裁剪后的搜索区域 (BGR格式)

        Returns:
            (x, y) 相对于 roi 的坐标，或 None
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """返回检测器名称（用于日志）"""
        pass

    def detect(self, img: np.ndarray, capture_area: dict) -> Optional[Tuple[int, int]]:
        """
        在图像中检测准星位置（公共接口）

        Args:
            img: BGR/BGRA 格式图像
            capture_area: 捕获区域 {'left', 'top', 'width', 'height'}

        Returns:
            (x, y) 屏幕绝对坐标，或 None
        """
        if not self.enabled:
            return None

        import cv2

        h, w = img.shape[:2]
        center_x, center_y = w // 2, h // 2

        # 1. 裁剪搜索区域
        x1 = max(0, center_x - self.search_radius)
        y1 = max(0, center_y - self.search_radius)
        x2 = min(w, center_x + self.search_radius)
        y2 = min(h, center_y + self.search_radius)

        roi = img[y1:y2, x1:x2]

        # 2. 转换为BGR
        if roi.shape[2] == 4:
            roi = cv2.cvtColor(roi, cv2.COLOR_BGRA2BGR)

        # 3. 调用子类实现
        local_pos = self._detect_impl(roi)

        if local_pos is None:
            self.last_valid_count -= 1
            if self.last_valid_count <= 0:
                self.last_pos = None
            return self.last_pos

        # 4. 转换为屏幕坐标
        abs_x_in_img = x1 + local_pos[0]
        abs_y_in_img = y1 + local_pos[1]

        screen_x = round(capture_area['left'] + abs_x_in_img)
        screen_y = round(capture_area['top'] + abs_y_in_img)

        # 5. 平滑处理
        if self.last_pos:
            screen_x = int(self.last_pos[0] * (1 - self.smooth_factor) + screen_x * self.smooth_factor)
            screen_y = int(self.last_pos[1] * (1 - self.smooth_factor) + screen_y * self.smooth_factor)

        self.last_pos = (screen_x, screen_y)
        self.last_valid_count = self.max_lost_frames
        return (screen_x, screen_y)

    def reset(self):
        """重置缓存"""
        self.last_pos = None
        self.last_valid_count = 0
