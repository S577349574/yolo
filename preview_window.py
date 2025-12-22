# preview_window.py (完整的多类别彩色版本)

import time
import cv2
import numpy as np
import threading
from queue import Queue, Empty
from typing import List, Dict, Optional, Tuple
import colorsys  # ⭐ 用于生成颜色

import utils
from config_manager import get_config


class PreviewWindow:
    """预览窗口管理类（支持多类别彩色显示）"""

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

        self.box_thickness = get_config('PREVIEW_BOX_THICKNESS', 2)
        self.text_scale = get_config('PREVIEW_TEXT_SCALE', 0.5)
        self.frame_skip = get_config('PREVIEW_FRAME_SKIP', 2)

        self._frame_counter = 0
        self._fps_history = []
        self._fps_max_samples = 30
        self._last_time = time.perf_counter()

        # ⭐⭐⭐ 多类别颜色系统 ⭐⭐⭐
        self._generate_class_colors()

        # 特殊状态颜色
        self.special_colors = {
            'locked': (0, 255, 0),  # 绿色 - 锁定状态
            'crosshair': (0, 0, 255),  # 红色 - 准心
            'aim_point': (255, 0, 255),  # 洋红 - 瞄准点
            'fps_good': (0, 255, 0),
            'fps_medium': (0, 165, 255),
            'fps_low': (0, 0, 255)
        }

        # 异步渲染支持（保持原有逻辑）
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
        utils.log(f"   快捷键: P=关闭, B=检测框, L=标签, F=FPS, H=高亮锁定")

    def _generate_class_colors(self):
        """为不同类别生成区分颜色"""
        self.class_colors = {}

        # ⭐ 方案1：预定义常见类别的固定颜色（推荐）
        predefined = {
            # 人体部位（你的模型）
            0: (255, 100, 255),  # body - 洋红/粉色
            1: (100, 255, 255),  # head - 青色/天蓝

            # 常见游戏类别（备用）
            2: (255, 255, 100),  # 类别2 - 黄色
            3: (255, 150, 100),  # 类别3 - 橙色
            4: (150, 100, 255),  # 类别4 - 紫色
            5: (100, 255, 150),  # 类别5 - 绿色
        }

        # ⭐ 方案2：为其他类别自动生成均匀分布的颜色
        for class_id in range(80):  # YOLO最多80类
            if class_id in predefined:
                self.class_colors[class_id] = predefined[class_id]
            else:
                # 使用HSV色彩空间，在色环上均匀分布
                hue = (class_id * 137.5) % 360  # 黄金角（137.5°）确保颜色均匀
                saturation = 0.9  # 高饱和度（鲜艳）
                value = 0.9  # 高明度（明亮）

                # HSV -> RGB -> BGR
                rgb = colorsys.hsv_to_rgb(hue / 360.0, saturation, value)
                bgr = tuple(int(c * 255) for c in reversed(rgb))
                self.class_colors[class_id] = bgr

        # 打印已定义的类别颜色（调试用）
        utils.log(f"   已生成 {len(self.class_colors)} 个类别颜色")
        for cid, color in predefined.items():
            utils.log(f"     类别{cid}: RGB{color[::-1]}")  # 打印RGB顺序

    def _get_box_color(self, class_id, is_target, is_locked):
        """
        获取检测框颜色（始终返回类别颜色）

        Args:
            class_id: 类别ID
            is_target: 是否为目标类别（未使用，保留接口兼容）
            is_locked: 是否已锁定（未使用，保留接口兼容）

        Returns:
            BGR颜色元组
        """
        # ⭐ 始终返回类别固定颜色（不再覆盖）
        return self.class_colors.get(class_id, (128, 128, 128))

    def update(
            self,
            img: np.ndarray,
            results: List[Dict],
            target_class_ids: Optional[List[int]] = None,
            best_target: Optional[Tuple[int, int]] = None,
            is_locked: bool = False,
            screen_center: Optional[Tuple[int, int]] = None,
            class_names: Optional[Dict[int, str]] = None,
            inference_fps: Optional[float] = None
    ) -> bool:
        """更新预览窗口（保持原有逻辑）"""
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
                    'target_class_ids': target_class_ids,
                    'best_target': best_target,
                    'is_locked': is_locked,
                    'screen_center': screen_center,
                    'class_names': class_names,
                    'inference_fps': inference_fps
                })
            except Exception as e:
                utils.log(f"⚠️ 预览队列错误: {e}")

            return self.enabled
        else:
            return self._render_frame(
                img, results, target_class_ids,
                best_target, is_locked, screen_center,
                class_names, inference_fps
            )

    def _render_loop(self):
        """渲染线程主循环（保持原有逻辑）"""
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, self.width, self.height)

        while not self._stop_event.is_set():
            try:
                frame_data = self._frame_queue.get(timeout=0.1)

                continue_preview = self._render_frame(
                    frame_data['img'],
                    frame_data['results'],
                    frame_data['target_class_ids'],
                    frame_data['best_target'],
                    frame_data['is_locked'],
                    frame_data['screen_center'],
                    frame_data['class_names'],
                    frame_data.get('inference_fps')
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
            target_class_ids: Optional[List[int]],
            best_target: Optional[Tuple[int, int]],
            is_locked: bool,
            screen_center: Optional[Tuple[int, int]],
            class_names: Optional[Dict[int, str]],
            inference_fps: Optional[float] = None
    ) -> bool:
        """实际渲染逻辑"""
        display_img = np.copy(img)

        if display_img.shape[2] == 4:
            display_img = cv2.cvtColor(display_img, cv2.COLOR_BGRA2BGR)

        h, w = display_img.shape[:2]

        # FPS
        current_fps = inference_fps if inference_fps is not None else self._calculate_fps()

        # 绘制检测框
        if self.show_boxes and results:
            self._draw_detections(
                display_img, results, target_class_ids, is_locked, class_names
            )

        # 绘制准心
        if self.show_crosshair and screen_center:
            self._draw_crosshair(display_img, screen_center, w, h)

        # 绘制瞄准点
        if self.show_aim_point and best_target and screen_center:
            self._draw_aim_point(display_img, best_target, screen_center, w, h)

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
        """绘制所有检测框（仅使用类别颜色）"""
        for result in results:
            class_id = result['class_id']
            box = result['box']
            x1, y1, x2, y2 = map(int, box)
            conf = result['confidence']

            is_target = not target_class_ids or class_id in target_class_ids

            # ⭐ 始终使用类别颜色
            color = self._get_box_color(class_id, is_target, is_locked)

            # ⭐ 锁定时只是加粗边框（不改颜色）
            if is_locked and is_target and self.highlight_targets:
                thickness = self.box_thickness + 2  # 加粗
            else:
                thickness = self.box_thickness

            cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)

            # ========== 绘制标签（保持不变）==========
            if self.show_labels or self.show_confidence:
                class_name = class_names.get(class_id, f"class_{class_id}") if class_names else f"ID:{class_id}"

                if self.show_labels and self.show_confidence:
                    label = f"{class_name} {conf:.2f}"
                elif self.show_labels:
                    label = class_name
                else:
                    label = f"{conf:.2f}"

                # 绘制文字背景
                (text_w, text_h), baseline = cv2.getTextSize(
                    label,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    self.text_scale,
                    1
                )

                cv2.rectangle(
                    img,
                    (x1, y1 - text_h - baseline - 4),
                    (x1 + text_w, y1),
                    color,
                    -1
                )

                # 文字颜色
                text_color = self._get_text_color(color)
                cv2.putText(
                    img,
                    label,
                    (x1, y1 - baseline - 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    self.text_scale,
                    text_color,
                    1,
                    cv2.LINE_AA
                )

    @staticmethod
    def _get_text_color(bg_color: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """根据背景颜色自动选择文字颜色（确保对比度）"""
        b, g, r = bg_color
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        return (0, 0, 0) if luminance > 128 else (255, 255, 255)

    def _draw_crosshair(self, img, screen_center, img_width, img_height):
        """绘制准心十字线"""
        center_x, center_y = img_width // 2, img_height // 2
        line_len, gap = 20, 5
        color = self.special_colors['crosshair']

        cv2.line(img, (center_x - line_len, center_y), (center_x - gap, center_y), color, 2)
        cv2.line(img, (center_x + gap, center_y), (center_x + line_len, center_y), color, 2)
        cv2.line(img, (center_x, center_y - line_len), (center_x, center_y - gap), color, 2)
        cv2.line(img, (center_x, center_y + gap), (center_x, center_y + line_len), color, 2)
        cv2.circle(img, (center_x, center_y), 2, color, -1)

    def _draw_aim_point(self, img, best_target, screen_center, img_width, img_height):
        """绘制瞄准点"""
        aim_x = best_target[0] - (screen_center[0] - img_width // 2)
        aim_y = best_target[1] - (screen_center[1] - img_height // 2)

        if 0 <= aim_x < img_width and 0 <= aim_y < img_height:
            color = self.special_colors['aim_point']
            cv2.circle(img, (int(aim_x), int(aim_y)), 6, color, 2)
            cv2.circle(img, (int(aim_x), int(aim_y)), 2, color, -1)
            cv2.line(img, (img_width // 2, img_height // 2),
                     (int(aim_x), int(aim_y)), color, 1, cv2.LINE_AA)

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
