# crosshair/base.py
"""
准星检测器抽象基类
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import numpy as np
from config.config_manager import get_config


class CrosshairDetector(ABC):
    """准星检测器抽象基类"""

    def __init__(self):
        self.enabled = get_config('ENABLE_CROSSHAIR_DETECTION', False)
        self.search_bounds = get_config('CROSSHAIR_SEARCH_BOUNDS', {
            'x_left': -80,
            'x_right': 80,
            'y_up': -80,
            'y_down': 80
        })
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
        if not self.enabled:
            return None

        import cv2

        if img is None or img.size == 0:
            return self.last_pos

        h, w = img.shape[:2]
        if h <= 0 or w <= 0:
            return self.last_pos

        center_x, center_y = w // 2, h // 2

        # 1) 规范化 bounds，防止配置写反
        xl = int(self.search_bounds.get('x_left', -80))
        xr = int(self.search_bounds.get('x_right', 80))
        yu = int(self.search_bounds.get('y_up', -80))
        yd = int(self.search_bounds.get('y_down', 80))

        if xr < xl:
            xl, xr = xr, xl
        if yd < yu:
            yu, yd = yd, yu

        # 2) 裁剪搜索区域
        x1 = max(0, min(w, center_x + xl))
        x2 = max(0, min(w, center_x + xr))
        y1 = max(0, min(h, center_y + yu))
        y2 = max(0, min(h, center_y + yd))

        if x2 <= x1 or y2 <= y1:
            # ROI 无效，按“未检测到”处理
            self.last_valid_count -= 1
            if self.last_valid_count <= 0:
                self.last_pos = None
            return self.last_pos

        roi = img[y1:y2, x1:x2]
        if roi is None or roi.size == 0:
            self.last_valid_count -= 1
            if self.last_valid_count <= 0:
                self.last_pos = None
            return self.last_pos

        # 3) 转换为 BGR（仅当确实有4通道）
        if roi.ndim == 3 and roi.shape[2] == 4:
            roi = cv2.cvtColor(roi, cv2.COLOR_BGRA2BGR)

        # 4) 调用子类实现
        local_pos = self._detect_impl(roi)
        if local_pos is None:
            self.last_valid_count -= 1
            if self.last_valid_count <= 0:
                self.last_pos = None
            return self.last_pos

        # 5) 转换为屏幕坐标
        abs_x_in_img = x1 + int(local_pos[0])
        abs_y_in_img = y1 + int(local_pos[1])

        screen_x = int(round(int(capture_area['left']) + abs_x_in_img))
        screen_y = int(round(int(capture_area['top']) + abs_y_in_img))

        # 6) 平滑
        if self.last_pos:
            screen_x = int(self.last_pos[0] * (1 - self.smooth_factor) + screen_x * self.smooth_factor)
            screen_y = int(self.last_pos[1] * (1 - self.smooth_factor) + screen_y * self.smooth_factor)

        self.last_pos = (screen_x, screen_y)
        self.last_valid_count = self.max_lost_frames
        return self.last_pos
