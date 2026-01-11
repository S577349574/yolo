"""
交互式准星校准工具 v3.19
优化：交互逻辑重构。左键采集点（首个点为中心），右键删除上一个采集点。
优化：采样点显示为紫色，采样范围掩码改为仅显示绿色轮廓，避免遮挡像素。
新增：配置文件生成全套过滤参数 (ROUNDNESS, SOLIDITY, MAX_DIST)
修复：KeyError 'center_bgr' 当缺少 sklearn 库时的崩溃问题
修复：【严重】调整参数时，工具自身的UI（如采样圈）会被截图库缓冲区更新捕获，导致自我干扰的问题。
"""
import json
import os
import platform
import time
from collections import Counter
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Dict

import cv2
import numpy as np

import utils
from image.image_source import create_image_source

# ============================================================
# OpenCV 窗口光标控制
# ============================================================
if platform.system() == 'Windows':
    import ctypes

    user32 = ctypes.windll.user32


    def set_window_cursor_blank(window_name: str):
        while user32.ShowCursor(False) >= 0:
            pass
        return None, None


    def restore_window_cursor(hwnd, original_cursor):
        while user32.ShowCursor(True) < 0:
            pass
else:
    def set_window_cursor_blank(window_name: str):
        return None, None


    def restore_window_cursor(hwnd, original_cursor):
        pass


@dataclass
class CrosshairSample:
    """准星样本数据"""
    center: Tuple[int, int]
    colors_bgr: List[Tuple[int, int, int]]
    colors_hsv: List[Tuple[int, int, int]]
    sample_points: List[Tuple[int, int]]


@dataclass
class ColorGroup:
    """颜色组"""
    name: str
    bgr_lower: Tuple[int, int, int]
    bgr_upper: Tuple[int, int, int]
    hsv_lower: Tuple[int, int, int]
    hsv_upper: Tuple[int, int, int]
    pixel_count: int


@dataclass
class CrosshairProfile:
    """准星特征配置"""
    name: str
    bgr_lower: Tuple[int, int, int]
    bgr_upper: Tuple[int, int, int]
    hsv_lower: Tuple[int, int, int]
    hsv_upper: Tuple[int, int, int]
    dominant_colors: List[Tuple[int, int, int]]
    color_groups: List[Dict]
    estimated_size: int
    sample_count: int
    created_at: str
    # 基础统计
    avg_pixel_count: int = 0
    # 过滤参数 (可微调)
    min_area: int = 0
    max_area: int = 0
    max_dist: int = 30
    min_solidity: float = 0.6
    min_roundness: float = 0.3


class CrosshairCalibrationTool:
    """
    准星校准工具 v3.19
    """

    def __init__(self, image_source=None):
        self.image_source = image_source
        self.samples: List[CrosshairSample] = []

        self.click_position: Optional[Tuple[int, int]] = None
        self.color_points: List[Tuple[int, int]] = []
        self.mouse_pos: Tuple[int, int] = (0, 0)

        self.sample_radius = 3
        self.min_radius = 1
        self.max_radius = 20
        self.color_tolerance = 50

        # 允许采样的最大半径（相对于左键中心）
        self.selection_range = 60

        self.profile_dir = "crosshair_profiles"
        os.makedirs(self.profile_dir, exist_ok=True)

        utils.log("🎯 准星校准工具 v3.19 初始化完成")

    def _mouse_callback(self, event, x, y, flags, param):
        self.mouse_pos = (x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            # 左键采集点
            if self.click_position is None:
                # 第一个点设为中心
                self.click_position = (x, y)
            else:
                # 后续点在范围内添加
                dist = np.sqrt((x - self.click_position[0]) ** 2 + (y - self.click_position[1]) ** 2)
                if dist <= self.selection_range:
                    self.color_points.append((x, y))
        elif event == cv2.EVENT_RBUTTONDOWN:
            # 右键删除上一个点
            if self.color_points:
                self.color_points.pop()
            else:
                self.click_position = None
        elif event == cv2.EVENT_MOUSEWHEEL:
            if flags > 0:
                self.sample_radius = min(self.max_radius, self.sample_radius + 1)
            else:
                self.sample_radius = max(self.min_radius, self.sample_radius - 1)

    def capture_samples(self, num_samples: int = 8) -> bool:
        utils.log(f"\n{'=' * 60}")
        utils.log(f"🎯 准星校准工具 v3.19")
        utils.log(f"{'=' * 60}")
        utils.log(f"   【左键】采集点（首点定中心，后续点采样）")
        utils.log(f"   【右键】撤销/删除上一个采集点")
        utils.log(f"   【滚轮】调节采样半径  【+/-】调节颜色容差")
        utils.log(f"   【C】清除所有  【Enter】确认样本  【Q】退出")
        utils.log(f"{'=' * 60}\n")

        input("按 Enter 开始采集...")

        if self.image_source is None:
            self.image_source = create_image_source()
            self._owns_image_source = True
        else:
            self._owns_image_source = False

        self.image_source.start()
        time.sleep(0.5)

        collected = 0

        try:
            while collected < num_samples:
                utils.log(f"\n📸 采集 {collected + 1}/{num_samples}")

                img = self._capture_frame()
                if img is None:
                    time.sleep(0.5)
                    continue

                result, sample = self._annotate_image(img, collected + 1, num_samples)

                if result == 'quit':
                    break
                elif result == 'skip':
                    time.sleep(0.3)
                    continue
                elif result == 'retry':
                    continue
                elif result == 'success' and sample:
                    self.samples.append(sample)
                    collected += 1
                    utils.log(f"   ✅ 采样点:{len(sample.sample_points)} 像素:{len(sample.colors_bgr)}")
                    time.sleep(0.3)

            cv2.destroyAllWindows()

            if len(self.samples) >= 3:
                utils.log(f"\n✅ 完成！共 {len(self.samples)} 个样本")
                return True
            else:
                utils.log(f"\n⚠️ 样本不足（至少3个）")
                return False

        finally:
            if self._owns_image_source and self.image_source:
                self.image_source.stop()
                self.image_source = None

    def _capture_frame(self) -> Optional[np.ndarray]:
        for _ in range(10):
            if self.image_source:
                frame = self.image_source.get_frame(timeout=0.1)
                if frame is not None:
                    if frame.ndim == 3 and frame.shape[2] == 4:
                        frame = frame[:, :, :3]
                    # ✅ 修复：强制返回副本，防止某些截图库（如dxcam）的后台缓冲区更新污染数据
                    return frame.copy()
            time.sleep(0.05)
        return None

    def _annotate_image(self, img_input: np.ndarray, current: int, total: int) -> Tuple[str, Optional[CrosshairSample]]:
        # ✅ 修复：创建图像副本，确保分析的是静态帧，不受UI绘制和屏幕刷新影响
        img = img_input.copy()

        self.click_position = None
        self.color_points = []

        window_name = f"Calibration ({current}/{total})"
        h, w = img.shape[:2]

        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, min(w * 2, 1200), min(h * 2, 900))
        cv2.setMouseCallback(window_name, self._mouse_callback)

        hwnd, original_cursor = set_window_cursor_blank(window_name)
        time.sleep(0.1)

        try:
            while True:
                display = img.copy()
                overlay = display.copy()

                all_colors = []
                all_sample_points = []

                if self.click_position:
                    # 绘制有效采样区范围（蓝色边界线，不填充）
                    cv2.circle(overlay, self.click_position, self.selection_range, (255, 200, 0), 1)
                    all_sample_points.append(self.click_position)

                all_sample_points.extend(self.color_points)

                combined_mask = np.zeros((h, w), dtype=np.uint8)

                for idx, (px, py) in enumerate(all_sample_points):
                    colors, mask = self._extract_similar_colors(
                        img, px, py, self.sample_radius, self.color_tolerance
                    )
                    all_colors.extend(colors)

                    if mask is not None:
                        x1 = max(0, px - self.sample_radius)
                        y1 = max(0, py - self.sample_radius)
                        x2 = min(w, px + self.sample_radius + 1)
                        y2 = min(h, py + self.sample_radius + 1)

                        mask_h, mask_w = mask.shape[:2]
                        region_h = y2 - y1
                        region_w = x2 - x1

                        if mask_h == region_h and mask_w == region_w:
                            mask_region = combined_mask[y1:y2, x1:x2]
                            combined_mask[y1:y2, x1:x2] = cv2.bitwise_or(mask_region, mask)

                    is_center = (idx == 0 and self.click_position is not None)
                    self._draw_sample_circle_overlay(overlay, px, py, is_center)

                # ✅ 优化：采样范围只显示轮廓线，避免遮挡像素
                if np.any(combined_mask):
                    contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    cv2.drawContours(display, contours, -1, (0, 255, 0), 1)

                mx, my = self.mouse_pos
                self._draw_mouse_circle_overlay(overlay, mx, my)
                cv2.addWeighted(overlay, 0.4, display, 0.6, 0, display)

                for idx, (px, py) in enumerate(all_sample_points):
                    is_center = (idx == 0 and self.click_position is not None)
                    self._draw_pixel_dot(display, px, py, is_center)

                self._draw_pixel_dot(display, mx, my, is_mouse=True)
                self._draw_status_bar(display, all_colors, w, h)

                cv2.imshow(window_name, display)
                key = cv2.waitKey(30) & 0xFF

                if key == ord('q') or key == ord('Q'):
                    return 'quit', None
                elif key == ord('s') or key == ord('S'):
                    return 'skip', None
                elif key == ord('r') or key == ord('R'):
                    return 'retry', None
                elif key == ord('c') or key == ord('C'):
                    self.click_position = None
                    self.color_points = []
                elif key == ord('+') or key == ord('='):
                    self.color_tolerance = min(100, self.color_tolerance + 5)
                elif key == ord('-') or key == ord('_'):
                    self.color_tolerance = max(10, self.color_tolerance - 5)
                elif key == 13 or key == 32:
                    if self.click_position and len(all_colors) >= 3:
                        sample = self._create_sample(all_colors, all_sample_points)
                        return 'success', sample

                try:
                    if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                        return 'quit', None
                except:
                    return 'quit', None

        finally:
            restore_window_cursor(hwnd, original_cursor)
            cv2.destroyWindow(window_name)

    def _draw_mouse_circle_overlay(self, overlay: np.ndarray, mx: int, my: int):
        cv2.circle(overlay, (mx, my), self.sample_radius, (0, 255, 0), 1)

    def _draw_sample_circle_overlay(self, overlay: np.ndarray, px: int, py: int, is_center: bool):
        # 采样点范围圆圈改为紫色细线
        color = (255, 0, 255) if not is_center else (0, 255, 0)
        cv2.circle(overlay, (px, py), self.sample_radius, color, 1)

    def _draw_pixel_dot(self, display: np.ndarray, x: int, y: int, is_center: bool = False, is_mouse: bool = False):
        h, w = display.shape[:2]
        if not (0 <= x < w and 0 <= y < h):
            return
        if is_mouse:
            color = (0, 255, 0)
        else:
            # ✅ 采集的点换成紫色
            color = (255, 0, 255)
        display[y, x] = color

    def _draw_status_bar(self, display: np.ndarray, colors: List, w: int, h: int):
        pixel_count = len(colors)
        points_count = 1 if self.click_position else 0
        points_count += len(self.color_points)

        if not self.click_position:
            status = "Step 1: Left Click to set Center"
            color = (0, 165, 255)
        elif pixel_count < 3:
            status = "Step 2: Left Click to sample Colors | Right Click to undo"
            color = (0, 200, 255)
        else:
            status = f"Ready | pts:{points_count} px:{pixel_count} [Enter] to Save | Right Click to undo"
            color = (0, 255, 0)

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.4
        thickness = 1
        (text_w, text_h), _ = cv2.getTextSize(status, font, font_scale, thickness)

        x = 10
        y = h - 10

        cv2.rectangle(display, (x - 5, y - text_h - 5), (x + text_w + 5, y + 5), (0, 0, 0), -1)
        cv2.addWeighted(display, 0.7, display, 0.3, 0, display)
        cv2.putText(display, status, (x, y), font, font_scale, color, thickness)

        if pixel_count >= 3:
            quantized = [(c[0] // 32 * 32, c[1] // 32 * 32, c[2] // 32 * 32) for c in colors]
            counter = Counter(quantized)
            top_colors = counter.most_common(4)
            block_x = w - 10 - len(top_colors) * 12
            block_y = y - text_h - 2
            for color_val, _ in top_colors:
                cv2.rectangle(display, (block_x, block_y), (block_x + 10, block_y + 10), color_val, -1)
                cv2.rectangle(display, (block_x, block_y), (block_x + 10, block_y + 10), (255, 255, 255), 1)
                block_x += 12

    def _extract_similar_colors(self, img: np.ndarray, cx: int, cy: int, radius: int, tolerance: int) -> Tuple[
        List[Tuple[int, int, int]], Optional[np.ndarray]]:
        h, w = img.shape[:2]
        if cx < 0 or cx >= w or cy < 0 or cy >= h:
            return [], None

        x1 = max(0, cx - radius)
        y1 = max(0, cy - radius)
        x2 = min(w, cx + radius + 1)
        y2 = min(h, cy + radius + 1)

        roi = img[y1:y2, x1:x2]
        if roi.size == 0:
            return [], None

        center_color = img[cy, cx].astype(np.float32)
        mask_h, mask_w = roi.shape[:2]
        local_cx = cx - x1
        local_cy = cy - y1

        circle_mask = np.zeros((mask_h, mask_w), dtype=np.uint8)
        cv2.circle(circle_mask, (local_cx, local_cy), radius, 255, -1)

        roi_float = roi.astype(np.float32)
        diff = np.sqrt(np.sum((roi_float - center_color) ** 2, axis=2))

        color_mask = (diff < tolerance).astype(np.uint8) * 255
        combined_mask = cv2.bitwise_and(circle_mask, color_mask)

        valid_pixels = roi[combined_mask > 0]
        colors = [tuple(int(x) for x in pixel) for pixel in valid_pixels]

        return colors, combined_mask

    def _create_sample(self, colors_bgr: List[Tuple[int, int, int]],
                       sample_points: List[Tuple[int, int]]) -> CrosshairSample:
        colors_hsv = []
        for bgr in colors_bgr:
            pixel = np.uint8([[bgr]])
            hsv = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0][0]
            colors_hsv.append(tuple(int(x) for x in hsv))

        return CrosshairSample(
            center=self.click_position,
            colors_bgr=colors_bgr,
            colors_hsv=colors_hsv,
            sample_points=sample_points
        )

    def analyze_and_generate_profile(self, profile_name: str = "custom") -> Optional[CrosshairProfile]:
        if len(self.samples) < 3:
            utils.log("⚠️ 样本不足")
            return None

        utils.log(f"\n{'=' * 60}")
        utils.log(f"🔬 分析准星特征...")
        utils.log(f"{'=' * 60}")

        all_bgr = []
        all_hsv = []
        for sample in self.samples:
            all_bgr.extend(sample.colors_bgr)
            all_hsv.extend(sample.colors_hsv)

        all_bgr = np.array(all_bgr)
        all_hsv = np.array(all_hsv)

        utils.log(f"   样本: {len(self.samples)} | 像素: {len(all_bgr)}")

        dominant_colors = self._find_dominant_colors(all_bgr, n_colors=5)
        utils.log(f"\n   🎨 主要颜色:")
        for i, (b, g, r) in enumerate(dominant_colors):
            utils.log(f"      {i + 1}. RGB({r},{g},{b})")

        color_groups = self._analyze_color_groups(all_bgr, all_hsv)
        utils.log(f"\n   📊 颜色组:")
        for group in color_groups:
            utils.log(f"      - {group['name']}: {group['pixel_count']}px")

        # =========================================================
        # 🔥 智能优化：自动锁定高饱和度颜色（去除白/灰芯干扰）
        # =========================================================
        best_group = None
        max_saturation = -1

        # 寻找饱和度最高的颜色组（红色饱和度高，白/灰色低）
        for group in color_groups:
            b, g, r = group['center_bgr']
            # 简单的饱和度估算: Max(RGB) - Min(RGB)
            saturation = max(b, g, r) - min(b, g, r)

            # 或者使用 HSV 的 S 通道更准确，但在 BGR 空间估算也够用了
            if saturation > max_saturation:
                max_saturation = saturation
                best_group = group

        # 如果找到了高饱和度的颜色（比如红色），且饱和度显著（>30），则只用该组作为主范围
        if best_group and max_saturation > 30:
            utils.log(f"\n   🧠 智能锁定: {best_group['name']} (排除杂色/白芯)")
            bgr_lower = best_group['bgr_lower']
            bgr_upper = best_group['bgr_upper']
            hsv_lower = best_group['hsv_lower']
            hsv_upper = best_group['hsv_upper']
        else:
            # 只有在全是黑白灰的情况下，才使用全局混合范围
            utils.log(f"\n   ⚠️ 未检测到鲜艳颜色，使用混合范围")
            bgr_lower, bgr_upper = self._calculate_tight_range(all_bgr)
            hsv_lower, hsv_upper = self._calculate_tight_hsv_range(all_hsv)
        # =========================================================

        avg_pixels = np.mean([len(s.colors_bgr) for s in self.samples])
        estimated_size = int(np.sqrt(avg_pixels) * 1.5)

        utils.log(f"   📏 尺寸: ~{estimated_size}px | 平均像素: {int(avg_pixels)}")

        # 计算默认过滤参数
        min_area = max(2, int(avg_pixels * 0.4))
        max_area = int(avg_pixels * 1.8)

        profile = CrosshairProfile(
            name=profile_name,
            bgr_lower=tuple(bgr_lower),
            bgr_upper=tuple(bgr_upper),
            hsv_lower=tuple(hsv_lower),
            hsv_upper=tuple(hsv_upper),
            dominant_colors=dominant_colors,
            color_groups=color_groups,
            estimated_size=estimated_size,
            sample_count=len(self.samples),
            created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            avg_pixel_count=int(avg_pixels),
            min_area=min_area,
            max_area=max_area,
            max_dist=30,
            # 🔥 针对红圈准星，降低实心度默认值
            min_solidity=0.4,
            min_roundness=0.25
        )

        self._save_profile(profile)
        return profile

    def _find_dominant_colors(self, colors: np.ndarray, n_colors: int = 5) -> List[Tuple[int, int, int]]:
        try:
            from sklearn.cluster import KMeans
            if len(colors) > 500:
                indices = np.random.choice(len(colors), 500, replace=False)
                colors_sample = colors[indices]
            else:
                colors_sample = colors
            n = min(n_colors, len(colors_sample))
            kmeans = KMeans(n_clusters=n, random_state=42, n_init=10)
            kmeans.fit(colors_sample)
            labels, counts = np.unique(kmeans.labels_, return_counts=True)
            sorted_idx = np.argsort(-counts)
            return [tuple(int(x) for x in kmeans.cluster_centers_[i]) for i in sorted_idx]
        except ImportError:
            quantized = [(int(c[0]) // 16 * 16, int(c[1]) // 16 * 16, int(c[2]) // 16 * 16) for c in colors]
            counter = Counter([tuple(c) for c in quantized])
            return [c for c, _ in counter.most_common(n_colors)]

    def _analyze_color_groups(self, colors_bgr: np.ndarray, colors_hsv: np.ndarray) -> List[Dict]:
        try:
            from sklearn.cluster import KMeans
            n_clusters = min(3, len(colors_bgr) // 10)
            if n_clusters < 2: n_clusters = 2
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = kmeans.fit_predict(colors_bgr)
            groups = []
            for i in range(n_clusters):
                mask = labels == i
                group_bgr = colors_bgr[mask]
                group_hsv = colors_hsv[mask]
                if len(group_bgr) < 3: continue
                bgr_lower, bgr_upper = self._calculate_tight_range(group_bgr)
                hsv_lower, hsv_upper = self._calculate_tight_hsv_range(group_hsv)
                center_bgr = kmeans.cluster_centers_[i]
                color_name = self._get_color_name(center_bgr)
                groups.append({
                    'name': color_name,
                    'bgr_lower': tuple(bgr_lower),
                    'bgr_upper': tuple(bgr_upper),
                    'hsv_lower': tuple(hsv_lower),
                    'hsv_upper': tuple(hsv_upper),
                    'pixel_count': int(np.sum(mask)),
                    'center_bgr': tuple(int(x) for x in center_bgr)
                })
            groups.sort(key=lambda x: x['pixel_count'], reverse=True)
            return groups
        except ImportError:
            bgr_lower, bgr_upper = self._calculate_tight_range(colors_bgr)
            hsv_lower, hsv_upper = self._calculate_tight_hsv_range(colors_hsv)

            # ✅ 修复：手动计算平均颜色作为 center_bgr
            if len(colors_bgr) > 0:
                mean_bgr = np.mean(colors_bgr, axis=0)
                center_bgr = tuple(int(x) for x in mean_bgr)
            else:
                center_bgr = (0, 0, 0)

            return [{'name': 'primary',
                     'bgr_lower': tuple(bgr_lower),
                     'bgr_upper': tuple(bgr_upper),
                     'hsv_lower': tuple(hsv_lower),
                     'hsv_upper': tuple(hsv_upper),
                     'pixel_count': len(colors_bgr),
                     'center_bgr': center_bgr}]  # 确保添加了 center_bgr

    def _get_color_name(self, bgr: np.ndarray) -> str:
        b, g, r = int(bgr[0]), int(bgr[1]), int(bgr[2])
        pixel = np.uint8([[[b, g, r]]])
        hsv = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0][0]
        h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])
        if s < 30: return "black" if v < 50 else "white" if v > 200 else "gray"
        if h < 10 or h >= 170:
            return "red"
        elif h < 25:
            return "orange"
        elif h < 35:
            return "yellow"
        elif h < 85:
            return "green"
        elif h < 100:
            return "cyan"
        elif h < 130:
            return "blue"
        elif h < 160:
            return "purple"
        else:
            return "pink"

    def _calculate_tight_range(self, colors: np.ndarray, margin: int = 15) -> Tuple[List[int], List[int]]:
        if len(colors) == 0: return [0, 0, 0], [255, 255, 255]
        lower = np.percentile(colors, 5, axis=0).astype(int)
        upper = np.percentile(colors, 95, axis=0).astype(int)
        lower = [max(0, int(x) - margin) for x in lower]
        upper = [min(255, int(x) + margin) for x in upper]
        return lower, upper

    def _calculate_tight_hsv_range(self, colors_hsv: np.ndarray) -> Tuple[List[int], List[int]]:
        if len(colors_hsv) == 0: return [0, 0, 0], [180, 255, 255]
        h, s, v = colors_hsv[:, 0], colors_hsv[:, 1], colors_hsv[:, 2]
        h_min, h_max = int(np.min(h)), int(np.max(h))
        if h_max - h_min > 90:
            h_shifted = np.where(h < 90, h + 180, h)
            h_lower = int(np.percentile(h_shifted, 5)) % 180
            h_upper = int(np.percentile(h_shifted, 95)) % 180
        else:
            h_lower = max(0, int(np.percentile(h, 5)) - 5)
            h_upper = min(180, int(np.percentile(h, 95)) + 5)
        s_lower = max(0, int(np.percentile(s, 5)) - 20)
        s_upper = min(255, int(np.percentile(s, 95)) + 20)
        v_lower = max(0, int(np.percentile(v, 5)) - 20)
        v_upper = min(255, int(np.percentile(v, 95)) + 20)
        return [h_lower, s_lower, v_lower], [h_upper, s_upper, v_upper]

    def _to_json_serializable(self, obj):
        if isinstance(obj, dict):
            return {k: self._to_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return tuple([self._to_json_serializable(item) for item in obj]) if isinstance(obj, tuple) else [
                self._to_json_serializable(item) for item in obj]
        elif isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return self._to_json_serializable(obj.tolist())
        else:
            return obj

    def _save_profile(self, profile: CrosshairProfile):
        json_path = os.path.join(self.profile_dir, f"{profile.name}.json")
        profile_dict = self._to_json_serializable(asdict(profile))
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(profile_dict, f, indent=2, ensure_ascii=False)
        utils.log(f"\n✅ 保存: {json_path}")
        self._generate_config_code(profile_dict)

    def _generate_config_code(self, profile_data: dict):
        color_groups_code = "[\n"
        for group in profile_data['color_groups']:
            color_groups_code += f"""    {{
        'name': '{group['name']}',
        'hsv_lower': {group['hsv_lower']},
        'hsv_upper': {group['hsv_upper']},
        'bgr_lower': {group['bgr_lower']},
        'bgr_upper': {group['bgr_upper']},
    }},
"""
        color_groups_code += "]"

        # 从 profile_data 获取最新的微调参数
        min_area = profile_data.get('min_area', 2)
        max_area = profile_data.get('max_area', 100)
        min_solid = profile_data.get('min_solidity', 0.6)
        min_round = profile_data.get('min_roundness', 0.3)
        max_dist = profile_data.get('max_dist', 30)

        code = f'''
# ============================================================
# 准星配置 (自动生成)
# 名称: {profile_data['name']} | 时间: {profile_data['created_at']}
# ============================================================

CROSSHAIR_PROFILE_NAME = '{profile_data['name']}'

CROSSHAIR_HSV_LOWER = {profile_data['hsv_lower']}
CROSSHAIR_HSV_UPPER = {profile_data['hsv_upper']}

CROSSHAIR_BGR_LOWER = {profile_data['bgr_lower']}
CROSSHAIR_BGR_UPPER = {profile_data['bgr_upper']}

CROSSHAIR_DOMINANT_COLORS = {profile_data['dominant_colors']}

CROSSHAIR_COLOR_GROUPS = {color_groups_code}

CROSSHAIR_SIZE = {profile_data['estimated_size']}

# ✅ 过滤参数 (已通过测试微调)
CROSSHAIR_MIN_AREA = {min_area}
CROSSHAIR_MAX_AREA = {max_area}
CROSSHAIR_MIN_SOLIDITY = {min_solid}
CROSSHAIR_MIN_ROUNDNESS = {min_round}
CROSSHAIR_MAX_DIST = {max_dist}
'''
        config_path = os.path.join(self.profile_dir, f"{profile_data['name']}_config.py")
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(code)
        utils.log(f"✅ 配置: {config_path}")
        print(f"\n{'=' * 50}")
        print(code)

    def load_profile(self, profile_name: str) -> Optional[CrosshairProfile]:
        json_path = os.path.join(self.profile_dir, f"{profile_name}.json")
        if not os.path.exists(json_path):
            utils.log(f"⚠️ 配置不存在: {json_path}")
            return None
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data['bgr_lower'] = tuple(data['bgr_lower'])
            data['bgr_upper'] = tuple(data['bgr_upper'])
            data['hsv_lower'] = tuple(data['hsv_lower'])
            data['hsv_upper'] = tuple(data['hsv_upper'])
            data['dominant_colors'] = [tuple(c) for c in data['dominant_colors']]
            if 'avg_pixel_count' not in data: data['avg_pixel_count'] = 10

            # 兼容旧配置：如果没有新的过滤字段，使用默认值
            if 'min_area' not in data: data['min_area'] = max(2, int(data['avg_pixel_count'] * 0.4))
            if 'max_area' not in data: data['max_area'] = int(data['avg_pixel_count'] * 1.8)
            if 'max_dist' not in data: data['max_dist'] = 30
            if 'min_solidity' not in data: data['min_solidity'] = 0.6
            if 'min_roundness' not in data: data['min_roundness'] = 0.3

            profile = CrosshairProfile(**data)
            utils.log(f"✅ 已加载: {profile_name}")
            return profile
        except Exception as e:
            utils.log(f"⚠️ 加载失败: {e}")
            return None

    def list_profiles(self) -> List[str]:
        profiles = []
        for f in os.listdir(self.profile_dir):
            if f.endswith('.json'): profiles.append(f[:-5])
        return profiles

    def test_detection(self, profile: CrosshairProfile) -> None:
        utils.log(f"\n🧪 测试检测 - {profile.name}")
        utils.log(f"按 Q 退出并保存调整后的参数")

        if self.image_source is None:
            self.image_source = create_image_source()
            self._owns_image_source = True
        else:
            self._owns_image_source = False

        self.image_source.start()
        time.sleep(0.5)

        window_name = "Detection Test"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        # 初始化参数
        cur_min_area = profile.min_area
        cur_max_area = profile.max_area
        cur_max_dist = profile.max_dist
        cur_min_solid = profile.min_solidity
        cur_min_round = profile.min_roundness

        # 内部固定阈值
        min_ratio, max_ratio = 0.5, 2.0
        last_log_time = 0

        # 记录是否进行了修改
        params_modified = False

        try:
            while True:
                frame = self._capture_frame()
                if frame is None:
                    time.sleep(0.05)
                    continue

                display = frame.copy()
                h, w = frame.shape[:2]
                center_x, center_y = w // 2, h // 2

                all_masks = []
                for group in profile.color_groups:
                    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                    lower = np.array(group['hsv_lower'])
                    upper = np.array(group['hsv_upper'])

                    if lower[0] > upper[0]:  # Red wrap-around
                        lower1 = np.array([lower[0], lower[1], lower[2]])
                        upper1 = np.array([180, upper[1], upper[2]])
                        mask1 = cv2.inRange(hsv, lower1, upper1)
                        lower2 = np.array([0, lower[1], lower[2]])
                        upper2 = np.array([upper[0], upper[1], upper[2]])
                        mask2 = cv2.inRange(hsv, lower2, upper2)
                        mask = cv2.bitwise_or(mask1, mask2)
                    else:
                        mask = cv2.inRange(hsv, lower, upper)
                    all_masks.append(mask)

                mask_pixel_count = 0
                contours_count = 0
                found_target = False
                reject_reason = ""

                cv2.circle(display, (center_x, center_y), cur_max_dist, (255, 200, 0), 1)

                if all_masks:
                    combined_mask = all_masks[0]
                    for mask in all_masks[1:]:
                        combined_mask = cv2.bitwise_or(combined_mask, mask)

                    # ✅ 优化：形态学开运算去除噪点
                    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
                    combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, kernel)

                    mask_pixel_count = cv2.countNonZero(combined_mask)
                    contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    contours_count = len(contours)
                    valid_contours = []

                    if contours:
                        for contour in contours:
                            area = cv2.contourArea(contour)
                            if area < cur_min_area: continue
                            if area > cur_max_area:
                                if not valid_contours: reject_reason = f"Too Big: {int(area)}px"
                                cv2.drawContours(display, [contour], -1, (0, 0, 255), 1)
                                continue

                            x, y, cw, ch = cv2.boundingRect(contour)
                            if cw == 0 or ch == 0: continue
                            ratio = cw / ch
                            if ratio < min_ratio or ratio > max_ratio:
                                if not valid_contours: reject_reason = f"Bad Ratio: {ratio:.1f}"
                                cv2.drawContours(display, [contour], -1, (100, 100, 100), 1)
                                continue

                            hull = cv2.convexHull(contour)
                            hull_area = cv2.contourArea(hull)
                            if hull_area > 0:
                                solidity = float(area) / hull_area
                                if solidity < cur_min_solid:
                                    if not valid_contours: reject_reason = f"Not Solid: {solidity:.2f}"
                                    cv2.drawContours(display, [contour], -1, (100, 100, 100), 1)
                                    continue

                            perimeter = cv2.arcLength(contour, True)
                            if perimeter == 0: continue
                            roundness = 4 * np.pi * area / (perimeter * perimeter)
                            if roundness < cur_min_round:
                                if not valid_contours: reject_reason = f"Not Round: {roundness:.2f}"
                                cv2.drawContours(display, [contour], -1, (100, 100, 100), 1)
                                continue

                            M = cv2.moments(contour)
                            if M['m00'] > 0:
                                cx = int(M['m10'] / M['m00'])
                                cy = int(M['m01'] / M['m00'])
                                dist = np.sqrt((cx - center_x) ** 2 + (cy - center_y) ** 2)
                                if dist > cur_max_dist:
                                    if not valid_contours: reject_reason = f"Too Far: {int(dist)}px"
                                    cv2.drawContours(display, [contour], -1, (100, 100, 100), 1)
                                    continue
                                valid_contours.append((dist, contour, cx, cy))

                    if valid_contours:
                        valid_contours.sort(key=lambda x: x[0])
                        best_dist, best_contour, cx, cy = valid_contours[0]
                        found_target = True
                        cv2.drawContours(display, [best_contour], -1, (0, 255, 0), 1)
                        cv2.circle(display, (cx, cy), 3, (0, 0, 255), -1)
                        cv2.putText(display, f"Dist:{int(best_dist)}px", (cx + 10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                                    (0, 255, 0), 1)

                    mask_small = cv2.resize(combined_mask, (w // 5, h // 5))
                    mask_colored = cv2.cvtColor(mask_small, cv2.COLOR_GRAY2BGR)
                    display[5:5 + h // 5, 5:5 + w // 5] = mask_colored
                    cv2.rectangle(display, (5, 5), (5 + w // 5, 5 + h // 5), (100, 100, 100), 1)

                status_color = (0, 255, 0) if found_target else (0, 0, 255)
                status_text = "DETECTED" if found_target else "NO TARGET"

                cv2.putText(display, f"Status: {status_text}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
                if not found_target and reject_reason:
                    cv2.putText(display, f"Reject: {reject_reason}", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                (0, 0, 255), 1)
                else:
                    cv2.putText(display, f"Mask Px: {mask_pixel_count}", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                (0, 255, 255), 1)

                # Dynamic Params Display
                cv2.putText(display, f"[1/2] Min Area: {cur_min_area}", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 255, 255), 1)
                cv2.putText(display, f"[3/4] Max Area: {cur_max_area}", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 255, 255), 1)
                cv2.putText(display, f"[W/S] Dist < {cur_max_dist} px", (10, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 255, 0), 1)
                cv2.putText(display, f"[A/D] Solid > {cur_min_solid:.2f}", (10, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 255, 0), 1)
                cv2.putText(display, f"[5/6] Round > {cur_min_round:.2f}", (10, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (255, 200, 0), 1)

                if params_modified:
                    cv2.putText(display, "Modified*", (w - 80, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)

                cv2.imshow(window_name, display)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'): break

                # Check for modifications
                prev_params = (cur_max_dist, cur_min_solid, cur_min_round, cur_min_area, cur_max_area)

                if key == ord('w'):
                    cur_max_dist = min(300, cur_max_dist + 5)
                elif key == ord('s'):
                    cur_max_dist = max(5, cur_max_dist - 5)
                elif key == ord('a'):
                    cur_min_solid = max(0.1, cur_min_solid - 0.05)
                elif key == ord('d'):
                    cur_min_solid = min(1.0, cur_min_solid + 0.05)
                elif key == ord('1'):
                    cur_min_area = max(1, cur_min_area - 1)
                elif key == ord('2'):
                    cur_min_area += 1
                elif key == ord('3'):
                    cur_max_area = max(cur_min_area + 1, cur_max_area - 5)
                elif key == ord('4'):
                    cur_max_area += 5
                elif key == ord('5'):
                    cur_min_round = max(0.0, cur_min_round - 0.05)
                elif key == ord('6'):
                    cur_min_round = min(1.0, cur_min_round + 0.05)

                if (cur_max_dist, cur_min_solid, cur_min_round, cur_min_area, cur_max_area) != prev_params:
                    params_modified = True

        finally:
            cv2.destroyWindow(window_name)
            if self._owns_image_source and self.image_source:
                self.image_source.stop()
                self.image_source = None

        # ✅ Save Modified Params Logic
        if params_modified:
            print("\n" + "=" * 50)
            print("检测到参数已修改，是否保存新参数到配置文件？")
            print(f"  Dist: {profile.max_dist} -> {cur_max_dist}")
            print(f"  Solid: {profile.min_solidity} -> {cur_min_solid:.2f}")
            print(f"  Round: {profile.min_roundness} -> {cur_min_round:.2f}")
            print(f"  Area: {profile.min_area}-{profile.max_area} -> {cur_min_area}-{cur_max_area}")
            print("=" * 50)
            save = input("保存更新? (y/n): ").strip().lower()
            if save == 'y':
                profile.max_dist = cur_max_dist
                profile.min_solidity = float(f"{cur_min_solid:.2f}")
                profile.min_roundness = float(f"{cur_min_round:.2f}")
                profile.min_area = cur_min_area
                profile.max_area = cur_max_area
                self._save_profile(profile)


def run_calibration():
    # ... existing run_calibration logic ...
    # (No changes needed here usually, just ensuring it calls the updated methods)
    utils.log("\n" + "=" * 50)
    utils.log("🎯 准星校准工具 v3.19")
    utils.log("=" * 50 + "\n")

    tool = CrosshairCalibrationTool()

    profiles = tool.list_profiles()
    if profiles:
        utils.log(f"📂 已有配置: {', '.join(profiles)}\n")

    print("选择操作:")
    print("  1. 新建校准")
    print("  2. 测试配置 (支持参数微调保存)")
    print("  3. 退出")

    choice = input("\n选项 (1/2/3): ").strip()

    if choice == '1':
        try:
            if tool.capture_samples(num_samples=6):
                name = input("\n配置名称 (Enter=默认): ").strip() or "my_crosshair"
                profile = tool.analyze_and_generate_profile(name)
                if profile:
                    test = input("\n测试效果? (y/n): ").strip().lower()
                    if test == 'y':
                        tool.test_detection(profile)
        except KeyboardInterrupt:
            utils.log("\n⚠️ 取消")
    elif choice == '2':
        if not profiles:
            utils.log("⚠️ 无配置")
            return
        print("\n配置列表:")
        for i, p in enumerate(profiles):
            print(f"  {i + 1}. {p}")
        idx = input("\n编号: ").strip()
        try:
            idx = int(idx) - 1
            if 0 <= idx < len(profiles):
                profile = tool.load_profile(profiles[idx])
                if profile:
                    tool.test_detection(profile)
        except ValueError:
            utils.log("⚠️ 无效选项")
    else:
        utils.log("👋 退出")


if __name__ == "__main__":
    run_calibration()