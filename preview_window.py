# preview_window.py (完整修复版 - 准星跟随检测位置 + 搜索区域固定)

import time
import cv2
import numpy as np
import threading
from queue import Queue, Empty
from typing import List, Dict, Optional, Tuple
import colorsys

import utils
from config_manager import get_config


class PreviewWindow:
    """预览窗口管理类（支持多类别彩色显示 + 准星检测可视化）"""

    def __init__(
            self,
            window_name: str = "YOLO Detection Preview",
            width: int = 800,
            height: int = 800,
            use_thread: bool = True
    ):
        self.window_name = window_name
        self.width = width
        self.height = height
        self.use_thread = use_thread
        self.enabled = True

        # 可视化选项
        self.show_boxes = get_config('PREVIEW_SHOW_BOXES', True)
        self.show_labels = get_config('PREVIEW_SHOW_LABELS', True)
        self.show_confidence = get_config('PREVIEW_SHOW_CONFIDENCE', True)
        self.show_fps = get_config('PREVIEW_SHOW_FPS', True)
        self.show_crosshair = get_config('PREVIEW_SHOW_CROSSHAIR', True)
        self.show_aim_point = get_config('PREVIEW_SHOW_AIM_POINT', True)
        self.show_all_classes = get_config('PREVIEW_SHOW_ALL_CLASSES', True)
        self.highlight_targets = get_config('PREVIEW_HIGHLIGHT_TARGETS', True)
        self.show_crosshair_detection = get_config('PREVIEW_SHOW_CROSSHAIR_DETECTION', True)
        self.show_search_area = get_config('PREVIEW_SHOW_SEARCH_AREA', True)
        self.box_thickness = get_config('PREVIEW_BOX_THICKNESS', 2)
        self.text_scale = get_config('PREVIEW_TEXT_SCALE', 0.5)
        self.frame_skip = get_config('PREVIEW_FRAME_SKIP', 2)

        self._frame_counter = 0
        self._fps_history = []
        self._fps_max_samples = 30
        self._last_time = time.perf_counter()

        # 多类别颜色系统
        self._generate_class_colors()

        # 特殊状态颜色
        self.special_colors = {
            'locked': (0, 255, 0),
            'crosshair': (0, 0, 255),  # 红色 - 真实准星位置
            'crosshair_detected': (0, 255, 255),  # 黄色 - 检测到的准星（调试用）
            'aim_point': (255, 0, 255),
            'search_area': (128, 128, 128),
            'fps_good': (0, 255, 0),
            'fps_medium': (0, 165, 255),
            'fps_low': (0, 0, 255)
        }

        # 异步渲染支持
        if self.use_thread:
            self._frame_queue = Queue(maxsize=2)
            self._stop_event = threading.Event()
            self._render_thread = threading.Thread(
                target=self._render_loop,
                daemon=True,
                name="PreviewRenderThread"
            )
            self._render_thread.start()
            utils.log(f"✅ 预览窗口已启动（异步模式）: {window_name}")
        else:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.window_name, self.width, self.height)
            utils.log(f"✅ 预览窗口已启动（同步模式）: {window_name}")

        utils.log(f"   多类别彩色显示已启用")
        utils.log(f"   准星检测可视化已启用")

    def _generate_class_colors(self):
        """为不同类别生成区分颜色"""
        self.class_colors = {}

        predefined = {
            0: (255, 100, 255),  # body - 洋红/粉色
            1: (100, 255, 255),  # head - 青色/天蓝
            2: (255, 255, 100),
            3: (255, 150, 100),
            4: (150, 100, 255),
            5: (100, 255, 150),
        }

        for class_id in range(80):
            if class_id in predefined:
                self.class_colors[class_id] = predefined[class_id]
            else:
                hue = (class_id * 137.5) % 360
                saturation = 0.9
                value = 0.9
                rgb = colorsys.hsv_to_rgb(hue / 360.0, saturation, value)
                bgr = tuple(int(c * 255) for c in reversed(rgb))
                self.class_colors[class_id] = bgr

    def _get_box_color(self, class_id, is_target, is_locked):
        """获取检测框颜色"""
        return self.class_colors.get(class_id, (128, 128, 128))

    def update(
            self,
            img: np.ndarray,
            results: List[Dict],
            capture_area: Dict[str, int],  # ✅ 新增参数
            target_class_ids: Optional[List[int]] = None,
            best_target: Optional[Tuple[int, int]] = None,
            is_locked: bool = False,
            screen_center: Optional[Tuple[int, int]] = None,
            class_names: Optional[Dict[int, str]] = None,
            inference_fps: Optional[float] = None,
            crosshair_position: Optional[Tuple[int, int]] = None
    ) -> bool:
        """更新预览窗口"""
        if not self.enabled:
            return False

        self._frame_counter += 1
        if self.frame_skip > 0 and self._frame_counter % (self.frame_skip + 1) != 0:
            return True

        if self.use_thread:
            try:
                if self._frame_queue.full():
                    try:
                        self._frame_queue.get_nowait()
                    except Empty:
                        pass

                self._frame_queue.put_nowait({
                    'img': img,
                    'results': results,
                    'capture_area': capture_area,  # ✅ 传递
                    'target_class_ids': target_class_ids,
                    'best_target': best_target,
                    'is_locked': is_locked,
                    'screen_center': screen_center,
                    'class_names': class_names,
                    'inference_fps': inference_fps,
                    'crosshair_position': crosshair_position
                })
            except Exception as e:
                utils.log(f"⚠️ 预览队列错误: {e}")

            return self.enabled
        else:
            return self._render_frame(
                img, results, capture_area,  # ✅ 传递
                target_class_ids, best_target, is_locked,
                screen_center, class_names, inference_fps,
                crosshair_position
            )

    def _render_loop(self):
        """渲染线程主循环"""
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, self.width, self.height)

        while not self._stop_event.is_set():
            try:
                frame_data = self._frame_queue.get(timeout=0.1)

                continue_preview = self._render_frame(
                    frame_data['img'],
                    frame_data['results'],
                    frame_data['capture_area'],  # ✅ 传递
                    frame_data['target_class_ids'],
                    frame_data['best_target'],
                    frame_data['is_locked'],
                    frame_data['screen_center'],
                    frame_data['class_names'],
                    frame_data.get('inference_fps'),
                    frame_data.get('crosshair_position')
                )

                if not continue_preview:
                    self.enabled = False
                    break

            except Empty:
                key = cv2.waitKey(10) & 0xFF
                if key == ord('p') or key == ord('P'):
                    utils.log("用户关闭预览窗口")
                    self.enabled = False
                    break
                elif key != 255:
                    self._handle_key(key)
            except Exception as e:
                utils.log(f"⚠️ 渲染线程错误: {e}")
                break

        try:
            cv2.destroyWindow(self.window_name)
        except Exception:
            pass

        utils.log("🛑 预览渲染线程已退出")

    def _render_frame(
            self,
            img: np.ndarray,
            results: List[Dict],
            capture_area: Dict[str, int],  # ✅ 新增参数
            target_class_ids: Optional[List[int]],
            best_target: Optional[Tuple[int, int]],
            is_locked: bool,
            screen_center: Optional[Tuple[int, int]],
            class_names: Optional[Dict[int, str]],
            inference_fps: Optional[float] = None,
            crosshair_position: Optional[Tuple[int, int]] = None
    ) -> bool:
        """实际渲染逻辑"""
        display_img = np.copy(img)

        if display_img.shape[2] == 4:
            display_img = cv2.cvtColor(display_img, cv2.COLOR_BGRA2BGR)

        h, w = display_img.shape[:2]
        current_fps = inference_fps if inference_fps is not None else self._calculate_fps()

        # 绘制检测框
        if self.show_boxes and results:
            self._draw_detections(
                display_img, results, target_class_ids, is_locked, class_names
            )

        # ✅ 绘制搜索区域（固定在图像中心）
        if self.show_search_area:
            self._draw_search_area(display_img, w, h)

        # ✅ 绘制真实准星位置（红色十字）
        if self.show_crosshair and screen_center:
            self._draw_crosshair(display_img, screen_center, capture_area)

        # 绘制瞄准点
        if self.show_aim_point and best_target and screen_center:
            self._draw_aim_point(display_img, best_target, screen_center, capture_area)

        # ⭐ 调试模式：显示检测到的准星原始位置（黄色）
        if crosshair_position and screen_center and self.show_crosshair_detection:
            offset_x = abs(crosshair_position[0] - screen_center[0])
            offset_y = abs(crosshair_position[1] - screen_center[1])

            if offset_x > 5 or offset_y > 5:
                self._draw_crosshair_detection(
                    display_img, crosshair_position, capture_area
                )

        # 绘制统计信息
        if self.show_fps:
            render_fps = self._calculate_fps() if inference_fps else None
            self._draw_stats(display_img, current_fps, len(results), is_locked, render_fps)

        cv2.imshow(self.window_name, display_img)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('p') or key == ord('P'):
            return False
        elif key != 255:
            self._handle_key(key)

        return True

    def _draw_detections(self, img, results, target_class_ids, is_locked, class_names):
        """绘制所有检测框"""
        for result in results:
            class_id = result['class_id']
            box = result['box']
            x1, y1, x2, y2 = map(int, box)
            conf = result['confidence']

            is_target = not target_class_ids or class_id in target_class_ids
            color = self._get_box_color(class_id, is_target, is_locked)

            if is_locked and is_target and self.highlight_targets:
                thickness = self.box_thickness + 2
            else:
                thickness = self.box_thickness

            cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)

            if self.show_labels or self.show_confidence:
                class_name = class_names.get(class_id, f"class_{class_id}") if class_names else f"ID:{class_id}"

                if self.show_labels and self.show_confidence:
                    label = f"{class_name} {conf:.2f}"
                elif self.show_labels:
                    label = class_name
                else:
                    label = f"{conf:.2f}"

                (text_w, text_h), baseline = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, self.text_scale, 1
                )

                cv2.rectangle(
                    img,
                    (x1, y1 - text_h - baseline - 4),
                    (x1 + text_w, y1),
                    color,
                    -1
                )

                text_color = self._get_text_color(color)
                cv2.putText(
                    img, label, (x1, y1 - baseline - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, self.text_scale,
                    text_color, 1, cv2.LINE_AA
                )

    @staticmethod
    def _get_text_color(bg_color: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """根据背景颜色自动选择文字颜色"""
        b, g, r = bg_color
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        return (0, 0, 0) if luminance > 128 else (255, 255, 255)

    def _draw_crosshair(
            self,
            img: np.ndarray,
            screen_center: Tuple[int, int],
            capture_area: Dict[str, int]  # ✅ 使用传入的 capture_area
    ):
        """
        绘制真实准星位置（红色十字）

        Args:
            screen_center: 屏幕坐标系的准星位置
            capture_area: 捕获区域信息
        """
        # ✅ 屏幕坐标 → 图像坐标
        crosshair_x = screen_center[0] - capture_area['left']
        crosshair_y = screen_center[1] - capture_area['top']

        # 边界检查
        h, w = img.shape[:2]
        if not (0 <= crosshair_x < w and 0 <= crosshair_y < h):
            return

        # 绘制十字线
        line_len = 20
        gap = 5
        thickness = 2
        center_size = 2
        color = self.special_colors['locked']  # 红色

        cv2.line(img, (crosshair_x - line_len, crosshair_y),
                 (crosshair_x - gap, crosshair_y), color, thickness)
        cv2.line(img, (crosshair_x + gap, crosshair_y),
                 (crosshair_x + line_len, crosshair_y), color, thickness)
        cv2.line(img, (crosshair_x, crosshair_y - line_len),
                 (crosshair_x, crosshair_y - gap), color, thickness)
        cv2.line(img, (crosshair_x, crosshair_y + gap),
                 (crosshair_x, crosshair_y + line_len), color, thickness)

        cv2.circle(img, (crosshair_x, crosshair_y), center_size, color, -1)

    def _draw_aim_point(
            self,
            img: np.ndarray,
            best_target: Tuple[int, int],
            screen_center: Tuple[int, int],
            capture_area: Dict[str, int]  # ✅ 使用传入的 capture_area
    ):
        """绘制瞄准点（洋红色）"""
        # ✅ 目标点坐标转换
        aim_x = best_target[0] - capture_area['left']
        aim_y = best_target[1] - capture_area['top']

        # 边界检查
        h, w = img.shape[:2]
        if not (0 <= aim_x < w and 0 <= aim_y < h):
            return

        color = self.special_colors['aim_point']

        # 绘制外圈和中心点
        cv2.circle(img, (int(aim_x), int(aim_y)), 6, color, 2)
        cv2.circle(img, (int(aim_x), int(aim_y)), 2, color, -1)

        # ✅ 准星位置坐标转换（用于绘制连线）
        crosshair_x = screen_center[0] - capture_area['left']
        crosshair_y = screen_center[1] - capture_area['top']

        # 绘制从准星到目标的连线
        cv2.line(
            img,
            (int(crosshair_x), int(crosshair_y)),
            (int(aim_x), int(aim_y)),
            color,
            1,
            cv2.LINE_AA
        )

    def _draw_crosshair_detection(
            self,
            img: np.ndarray,
            crosshair_pos: Tuple[int, int],
            capture_area: Dict[str, int]  # ✅ 使用传入的 capture_area
    ):
        """
        ⭐ 调试模式:绘制检测到的准星原始位置（黄色标记）
        仅在准星有偏移时显示，用于验证检测结果
        """
        # ✅ 屏幕坐标 → 图像坐标
        crosshair_x = crosshair_pos[0] - capture_area['left']
        crosshair_y = crosshair_pos[1] - capture_area['top']

        # 边界检查
        h, w = img.shape[:2]
        if not (0 <= crosshair_x < w and 0 <= crosshair_y < h):
            return

        color = self.special_colors['crosshair_detected']  # 黄色

        # 绘制小十字标记
        cv2.drawMarker(
            img,
            (int(crosshair_x), int(crosshair_y)),
            color,
            markerType=cv2.MARKER_DIAMOND,
            markerSize=15,
            thickness=1,
            line_type=cv2.LINE_AA
        )

        # 绘制标签
        label = "DETECTED"
        label_x = int(crosshair_x) + 20
        label_y = int(crosshair_y) - 10

        cv2.putText(
            img, label, (label_x, label_y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4,
            color, 1, cv2.LINE_AA
        )

    def _draw_search_area(
            self,
            img: np.ndarray,
            img_width: int,
            img_height: int
    ):
        """
        ✅ 绘制准星搜索区域（固定在图像中心）

        注意：此区域表示检测器实际的搜索范围，不会跟随准星移动
        """
        from config_manager import get_config
        bounds = get_config('CROSSHAIR_SEARCH_BOUNDS', {
            'x_left': -30,
            'x_right': 30,
            'y_up': -150,
            'y_down': 20
        })

        # ✅ 固定使用图像中心
        center_x = img_width // 2
        center_y = img_height // 2

        # 计算搜索区域边界
        search_x1 = max(0, center_x + bounds['x_left'])
        search_x2 = min(img_width - 1, center_x + bounds['x_right'])
        search_y1 = max(0, center_y + bounds['y_up'])
        search_y2 = min(img_height - 1, center_y + bounds['y_down'])

        # 绘制虚线矩形
        color = self.special_colors['search_area']  # 灰色
        self._draw_dashed_rectangle(
            img,
            (search_x1, search_y1),
            (search_x2, search_y2),
            color,
            thickness=1,
            dash_length=10
        )

        # 添加标签说明
        label = "Search Area"
        label_pos = (search_x1 + 5, search_y1 - 5)
        cv2.putText(
            img, label, label_pos,
            cv2.FONT_HERSHEY_SIMPLEX, 0.4,
            color, 1, cv2.LINE_AA
        )

    def _draw_stats(self, img, fps, detection_count, is_locked, render_fps=None):
        """绘制统计信息"""
        if fps >= 200:
            fps_color = self.special_colors['fps_good']
        elif fps >= 100:
            fps_color = self.special_colors['fps_medium']
        else:
            fps_color = self.special_colors['fps_low']

        info_lines = [f"Inference: {fps:.1f} FPS"]
        if render_fps:
            info_lines.append(f"Render: {render_fps:.1f} FPS")
        info_lines.extend([
            f"Detections: {detection_count}",
            f"Status: {'LOCKED' if is_locked else 'TRACKING'}"
        ])

        overlay = img.copy()
        bg_height = len(info_lines) * 25 + 10
        cv2.rectangle(overlay, (10, 10), (250, bg_height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)

        for i, line in enumerate(info_lines):
            color = fps_color if i == 0 else (255, 255, 255)
            cv2.putText(img, line, (15, 30 + i * 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

    def _calculate_fps(self) -> float:
        """计算FPS"""
        current_time = time.perf_counter()
        delta = current_time - self._last_time
        self._last_time = current_time

        if delta > 0:
            fps = 1.0 / delta
            self._fps_history.append(fps)
            if len(self._fps_history) > self._fps_max_samples:
                self._fps_history.pop(0)
            return sum(self._fps_history) / len(self._fps_history)
        return 0.0

    def _handle_key(self, key: int):
        """处理快捷键"""
        if key == ord('b') or key == ord('B'):
            self.show_boxes = not self.show_boxes
            utils.log(f"检测框: {'开' if self.show_boxes else '关'}")
        elif key == ord('l') or key == ord('L'):
            self.show_labels = not self.show_labels
            utils.log(f"标签: {'开' if self.show_labels else '关'}")
        elif key == ord('f') or key == ord('F'):
            self.show_fps = not self.show_fps
            utils.log(f"FPS: {'开' if self.show_fps else '关'}")
        elif key == ord('h') or key == ord('H'):
            self.highlight_targets = not self.highlight_targets
            utils.log(f"高亮锁定: {'开' if self.highlight_targets else '关'}")
        elif key == ord('c') or key == ord('C'):
            self.show_crosshair_detection = not self.show_crosshair_detection
            utils.log(f"准星检测显示: {'开' if self.show_crosshair_detection else '关'}")
        elif key == ord('s') or key == ord('S'):
            self.show_search_area = not self.show_search_area
            utils.log(f"准星搜索区域: {'开' if self.show_search_area else '关'}")

    def _draw_dashed_rectangle(
            self,
            img: np.ndarray,
            pt1: Tuple[int, int],
            pt2: Tuple[int, int],
            color: Tuple[int, int, int],
            thickness: int = 1,
            dash_length: int = 10
    ):
        """绘制虚线矩形"""
        x1, y1 = pt1
        x2, y2 = pt2

        # 绘制四条边（虚线）
        self._draw_dashed_line(img, (x1, y1), (x2, y1), color, thickness, dash_length)
        self._draw_dashed_line(img, (x1, y2), (x2, y2), color, thickness, dash_length)
        self._draw_dashed_line(img, (x1, y1), (x1, y2), color, thickness, dash_length)
        self._draw_dashed_line(img, (x2, y1), (x2, y2), color, thickness, dash_length)

    def _draw_dashed_line(
            self,
            img: np.ndarray,
            pt1: Tuple[int, int],
            pt2: Tuple[int, int],
            color: Tuple[int, int, int],
            thickness: int = 1,
            dash_length: int = 10
    ):
        """绘制虚线"""
        x1, y1 = pt1
        x2, y2 = pt2

        dx = x2 - x1
        dy = y2 - y1
        length = np.sqrt(dx ** 2 + dy ** 2)

        if length == 0:
            return

        ux = dx / length
        uy = dy / length

        current_length = 0
        is_dash = True

        while current_length < length:
            segment_length = min(dash_length, length - current_length)

            if is_dash:
                start_x = int(x1 + ux * current_length)
                start_y = int(y1 + uy * current_length)
                end_x = int(x1 + ux * (current_length + segment_length))
                end_y = int(y1 + uy * (current_length + segment_length))

                cv2.line(img, (start_x, start_y), (end_x, end_y), color, thickness, cv2.LINE_AA)

            current_length += segment_length
            is_dash = not is_dash

    def close(self):
        """关闭窗口"""
        self.enabled = False
        if self.use_thread:
            self._stop_event.set()
            if self._render_thread.is_alive():
                self._render_thread.join(timeout=2.0)
        else:
            try:
                cv2.destroyWindow(self.window_name)
            except Exception:
                pass
        utils.log(f"✅ 预览窗口已关闭")
