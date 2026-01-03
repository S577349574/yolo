# crosshair/detectors/template_detector.py
"""
模板匹配准星检测器（颜色预过滤增强版）
"""
import cv2
import numpy as np
import os
from typing import Optional, Tuple
from ..base import CrosshairDetector
from config_manager import get_config
import utils


class TemplateCrosshairDetector(CrosshairDetector):
    """基于模板匹配的准星检测（颜色预过滤增强版）"""

    def __init__(self, template_path: str = None, template_img: np.ndarray = None,
                 target_color_bgr: tuple = None, target_color_name: str = None):
        super().__init__()

        self.threshold = get_config('CROSSHAIR_MATCH_THRESHOLD', 0.75)
        self.search_radius = 80
        self.smooth_factor = 0.2

        # ===== 颜色过滤相关 =====
        self.target_color_bgr = target_color_bgr
        self.target_color_name = target_color_name
        self.color_tolerance = 40
        self.enable_color_filter = (target_color_bgr is not None)

        # ===== 位置跟踪相关 =====
        self.last_position = None
        self.confidence_history = []
        self.priority_search_radius = 40
        self.fallback_search_radius = 80
        self.tracking_lost_frames = 0
        self.max_lost_frames = 3

        self._frame_count = 0

        self.template = None
        self.template_gray = None
        self.template_mask = None
        self.template_w = 0
        self.template_h = 0

        if template_img is not None:
            self._set_template(template_img)
        elif template_path and os.path.exists(template_path):
            self._load_template(template_path)
        else:
            default_path = get_config('CROSSHAIR_TEMPLATE_PATH', 'templates/crosshair.png')
            if os.path.exists(default_path):
                self._load_template(default_path)

        if self.enable_color_filter:
            utils.log(f"   🎨 颜色过滤已启用:")
            utils.log(f"      目标颜色: {self.target_color_name} {self.target_color_bgr}")
            utils.log(f"      颜色容差: ±{self.color_tolerance}")
            lower, upper = self._get_color_range()
            utils.log(f"      有效范围: {lower} ~ {upper}")
        else:
            utils.log(f"   ⚠️ 颜色过滤未启用（未提供目标颜色）")

    def get_name(self) -> str:
        return "模板准星检测器（颜色预过滤版）"

    def _set_template(self, template_bgr: np.ndarray):
        """设置模板并裁剪出准星区域"""
        has_alpha = template_bgr.shape[2] == 4 if len(template_bgr.shape) == 3 else False

        if has_alpha:
            alpha = template_bgr[:, :, 3]
            rows = np.any(alpha > 0, axis=1)
            cols = np.any(alpha > 0, axis=0)

            if not np.any(rows) or not np.any(cols):
                utils.log("   ⚠️ 模板完全透明，使用原始尺寸")
                template_bgr = cv2.cvtColor(template_bgr, cv2.COLOR_BGRA2BGR)
                template_gray_full = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
                _, mask = cv2.threshold(template_gray_full, 30, 255, cv2.THRESH_BINARY)

                self.template = template_bgr
                self.template_gray = template_gray_full
                self.template_mask = mask
                self.template_h, self.template_w = template_gray_full.shape
                self.enabled = True
                return

            y_min, y_max = np.where(rows)[0][[0, -1]]
            x_min, x_max = np.where(cols)[0][[0, -1]]

            margin = 5
            h, w = template_bgr.shape[:2]
            y_min = max(0, y_min - margin)
            y_max = min(h, y_max + margin + 1)
            x_min = max(0, x_min - margin)
            x_max = min(w, x_max + margin + 1)

            template_cropped_bgra = template_bgr[y_min:y_max, x_min:x_max]
            template_bgr_cropped = cv2.cvtColor(template_cropped_bgra, cv2.COLOR_BGRA2BGR)
            alpha_cropped = template_cropped_bgra[:, :, 3]
            mask = (alpha_cropped > 0).astype(np.uint8) * 255
            template_gray = cv2.cvtColor(template_bgr_cropped, cv2.COLOR_BGR2GRAY)

            non_zero = np.sum(mask > 0)
            total = mask.size

            utils.log(f"   ✅ 准星已裁剪（基于Alpha）: {template_bgr_cropped.shape[1]}x{template_bgr_cropped.shape[0]} "
                      f"(有效像素 {non_zero}/{total}, {non_zero / total * 100:.1f}%)")

            self.template = template_bgr_cropped
            self.template_gray = template_gray
            self.template_mask = mask
            self.template_h, self.template_w = template_gray.shape

        else:
            utils.log("   ⚠️ 模板没有Alpha通道，使用颜色阈值裁剪")
            template_gray_full = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(template_gray_full, 30, 255, cv2.THRESH_BINARY)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                utils.log("   ❌ 未检测到准星轮廓，使用原始模板")
                self.template = template_bgr
                self.template_gray = template_gray_full
                self.template_mask = mask
                self.template_h, self.template_w = template_gray_full.shape
                self.enabled = True
                return

            x, y, w, h = cv2.boundingRect(np.vstack(contours))
            margin = 5
            x = max(0, x - margin)
            y = max(0, y - margin)
            w = min(template_bgr.shape[1] - x, w + 2 * margin)
            h = min(template_bgr.shape[0] - y, h + 2 * margin)

            self.template = template_bgr[y:y + h, x:x + w]
            self.template_gray = template_gray_full[y:y + h, x:x + w]
            self.template_mask = mask[y:y + h, x:x + w]
            self.template_h, self.template_w = self.template_gray.shape

            non_zero = cv2.countNonZero(self.template_mask)
            total = self.template_w * self.template_h

            utils.log(f"   ✅ 准星已裁剪: {self.template_w}x{self.template_h} "
                      f"(有效像素 {non_zero}/{total}, {non_zero / total * 100:.1f}%)")

        self.enabled = True

    def _load_template(self, path: str):
        """从文件加载模板"""
        if not os.path.exists(path):
            utils.log(f"   ⚠️ 模板文件不存在: {path}")
            self.enabled = False
            return

        template = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if template is None:
            utils.log(f"   ❌ 无法读取模板文件: {path}")
            self.enabled = False
            return

        self._set_template(template)
        utils.log(f"   ✅ 模板加载成功: {path} ({self.template_w}x{self.template_h})")

    def set_template(self, template_bgr: np.ndarray):
        """公开的设置模板方法"""
        self._set_template(template_bgr)

    def _get_color_range(self) -> Tuple[np.ndarray, np.ndarray]:
        """计算颜色过滤的上下界"""
        if self.target_color_bgr is None:
            return None, None

        lower = np.array([max(0, c - self.color_tolerance) for c in self.target_color_bgr])
        upper = np.array([min(255, c + self.color_tolerance) for c in self.target_color_bgr])

        return lower, upper

    def _apply_color_filter(self, img: np.ndarray) -> np.ndarray:
        """应用颜色过滤"""
        if not self.enable_color_filter:
            return img

        lower, upper = self._get_color_range()
        mask = cv2.inRange(img, lower, upper)
        filtered = cv2.bitwise_and(img, img, mask=mask)
        return filtered

    def _detect_impl(self, roi: np.ndarray) -> Optional[Tuple[int, int]]:
        """实现检测逻辑"""
        self._frame_count += 1

        if self.template_gray is None:
            return None

        # 颜色预过滤
        if self.enable_color_filter:
            roi_filtered = self._apply_color_filter(roi)
            roi_gray = cv2.cvtColor(roi_filtered, cv2.COLOR_BGR2GRAY)
            if cv2.countNonZero(roi_gray) < 10:
                return None
        else:
            roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        if roi_gray.shape[0] < self.template_h or roi_gray.shape[1] < self.template_w:
            return None

        # 快速搜索
        if self.last_position is not None:
            result = self._search_near_position(
                roi_gray,
                self.last_position,
                self.priority_search_radius,
                roi
            )

            if result is not None:
                cx, cy, confidence = result

                # 检查置信度下降趋势
                if len(self.confidence_history) >= 3:
                    recent_avg = sum(self.confidence_history[-3:]) / 3
                    if confidence < recent_avg - 0.1:
                        global_result = self._full_search(roi_gray)
                        if global_result is not None:
                            g_cx, g_cy, g_conf = global_result
                            if g_conf > confidence + 0.05:
                                self._update_tracking(g_cx, g_cy, g_conf)
                                return (g_cx, g_cy)

                # 检查位置跳变
                distance = np.sqrt((cx - self.last_position[0]) ** 2 + (cy - self.last_position[1]) ** 2)
                if distance > 50:
                    global_result = self._full_search(roi_gray)
                    if global_result is not None:
                        g_cx, g_cy, g_conf = global_result
                        distance_to_global = np.sqrt((cx - g_cx) ** 2 + (cy - g_cy) ** 2)
                        if distance_to_global > 30:
                            self._update_tracking(g_cx, g_cy, g_conf)
                            return (g_cx, g_cy)

                # 周期性全局验证
                if self._frame_count % 60 == 0:
                    global_result = self._full_search(roi_gray)
                    if global_result is not None:
                        g_cx, g_cy, g_conf = global_result
                        distance_to_global = np.sqrt((cx - g_cx) ** 2 + (cy - g_cy) ** 2)
                        if distance_to_global > 20 or g_conf > confidence + 0.1:
                            self._update_tracking(g_cx, g_cy, g_conf)
                            return (g_cx, g_cy)

                self._update_tracking(cx, cy, confidence)
                return (cx, cy)

        # 全局搜索
        result = self._full_search(roi_gray)
        if result is not None:
            cx, cy, confidence = result
            self._update_tracking(cx, cy, confidence)
            return (cx, cy)

        # 检测失败
        self.last_position = None
        self.confidence_history.clear()
        return None

    def _search_near_position(self, roi_gray: np.ndarray, center: Tuple[int, int],
                              radius: int, original_roi: np.ndarray = None) -> Optional[Tuple[int, int, float]]:
        """在指定位置附近小范围搜索"""
        cx, cy = center

        x1 = max(0, cx - radius)
        y1 = max(0, cy - radius)
        x2 = min(roi_gray.shape[1], cx + radius)
        y2 = min(roi_gray.shape[0], cy + radius)

        search_roi = roi_gray[y1:y2, x1:x2]

        if search_roi.shape[0] < self.template_h or search_roi.shape[1] < self.template_w:
            return None

        result = cv2.matchTemplate(
            search_roi,
            self.template_gray,
            cv2.TM_SQDIFF,
            mask=self.template_mask
        )

        min_val, _, min_loc, _ = cv2.minMaxLoc(result)
        normalized_score = 1.0 - (min_val / (self.template_w * self.template_h * 255 * 255))

        if normalized_score < self.threshold:
            return None

        local_cx = min_loc[0] + self.template_w // 2
        local_cy = min_loc[1] + self.template_h // 2
        global_cx = x1 + local_cx
        global_cy = y1 + local_cy

        return (global_cx, global_cy, normalized_score)

    def _full_search(self, roi_gray: np.ndarray) -> Optional[Tuple[int, int, float]]:
        """全局搜索"""
        result = cv2.matchTemplate(
            roi_gray,
            self.template_gray,
            cv2.TM_SQDIFF,
            mask=self.template_mask
        )

        min_val, _, min_loc, _ = cv2.minMaxLoc(result)
        normalized_score = 1.0 - (min_val / (self.template_w * self.template_h * 255 * 255))

        if normalized_score < self.threshold:
            return None

        cx = min_loc[0] + self.template_w // 2
        cy = min_loc[1] + self.template_h // 2

        return (cx, cy, normalized_score)

    def _update_tracking(self, cx: int, cy: int, confidence: float):
        """更新跟踪状态"""
        self.last_position = (cx, cy)
        self.confidence_history.append(confidence)
        self.tracking_lost_frames = 0

        if len(self.confidence_history) > 10:
            self.confidence_history.pop(0)
