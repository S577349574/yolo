# crosshair_visualizer.py (修复版)
"""
Valorant 准星可视化工具
"""
import numpy as np
import cv2
from typing import Dict
from PIL import Image
from crosshair.games.valorant.valorant_colors import hex_to_bgr


class CrosshairVisualizer:
    """准星可视化器"""

    @staticmethod
    def render(config: Dict, color: tuple = None, size: int = 600) -> np.ndarray:
        """渲染准星到透明背景图像"""
        # 创建透明画布
        img = np.zeros((size, size, 4), dtype=np.uint8)
        center = size // 2

        # 从 color_hex 转换为 BGR
        if color is None:
            color_hex = config.get('color_hex', '#FFFFFF')
            color = hex_to_bgr(color_hex)

        # 黑色描边
        outline_color = (0, 0, 0, 255)
        outline_thickness = int(config['outline']['thickness']) if config['outline']['enabled'] else 0

        # 1. 绘制外线 (Outer Lines)
        if config['outer_lines']['enabled']:
            outer = config['outer_lines']
            outer_start = int(outer['offset'])
            outer_length = int(outer['length'])
            outer_thickness = int(outer['thickness'])
            outer_alpha = int(outer['opacity'] * 255)
            outer_color = (*color, outer_alpha)

            # 四个方向（外线通常上下左右一致）
            CrosshairVisualizer._draw_line_with_outline(
                img, center, center - outer_start, 0, -outer_length,
                outer_thickness, outer_color, outline_thickness, outline_color
            )
            CrosshairVisualizer._draw_line_with_outline(
                img, center, center + outer_start, 0, outer_length,
                outer_thickness, outer_color, outline_thickness, outline_color
            )
            CrosshairVisualizer._draw_line_with_outline(
                img, center - outer_start, center, -outer_length, 0,
                outer_thickness, outer_color, outline_thickness, outline_color
            )
            CrosshairVisualizer._draw_line_with_outline(
                img, center + outer_start, center, outer_length, 0,
                outer_thickness, outer_color, outline_thickness, outline_color
            )

        # 2. 绘制内线 (Inner Lines) ⭐ 修复：区分上下和左右长度
        if config['inner_lines']['enabled']:
            inner = config['inner_lines']
            inner_start = int(inner['offset'])
            inner_horizontal_length = int(inner['length'])  # ⭐ 左右长度
            inner_vertical_length = int(inner.get('vertical_length', inner['length']))  # ⭐ 上下长度
            inner_thickness = int(inner['thickness'])
            inner_alpha = int(inner['opacity'] * 255)
            inner_color = (*color, inner_alpha)

            # ⭐ 上线（使用 vertical_length）
            CrosshairVisualizer._draw_line_with_outline(
                img, center, center - inner_start, 0, -inner_vertical_length,
                inner_thickness, inner_color, outline_thickness, outline_color
            )

            # ⭐ 下线（使用 vertical_length）
            CrosshairVisualizer._draw_line_with_outline(
                img, center, center + inner_start, 0, inner_vertical_length,
                inner_thickness, inner_color, outline_thickness, outline_color
            )

            # ⭐ 左线（使用 horizontal_length）
            CrosshairVisualizer._draw_line_with_outline(
                img, center - inner_start, center, -inner_horizontal_length, 0,
                inner_thickness, inner_color, outline_thickness, outline_color
            )

            # ⭐ 右线（使用 horizontal_length）
            CrosshairVisualizer._draw_line_with_outline(
                img, center + inner_start, center, inner_horizontal_length, 0,
                inner_thickness, inner_color, outline_thickness, outline_color
            )

        # 3. 绘制中心点 (Center Dot)
        if config['center_dot']['enabled']:
            dot_thickness = int(config['center_dot']['thickness'])
            dot_alpha = int(config['center_dot'].get('opacity', 1.0) * 255)
            dot_color = (*color, dot_alpha)

            # 绘制描边
            if outline_thickness > 0:
                y1 = max(0, center - dot_thickness // 2 - outline_thickness)
                y2 = min(img.shape[0], center + dot_thickness // 2 + outline_thickness)
                x1 = max(0, center - dot_thickness // 2 - outline_thickness)
                x2 = min(img.shape[1], center + dot_thickness // 2 + outline_thickness)
                img[y1:y2, x1:x2] = outline_color

            # 绘制中心点
            y1 = max(0, center - dot_thickness // 2)
            y2 = min(img.shape[0], center + dot_thickness // 2)
            x1 = max(0, center - dot_thickness // 2)
            x2 = min(img.shape[1], center + dot_thickness // 2)
            img[y1:y2, x1:x2] = dot_color

        return img

    @staticmethod
    def _draw_line_with_outline(img, start_x, start_y, dx, dy, thickness, color, outline, outline_color):
        """
        绘制带描边的线条
        """
        start_x = int(start_x)
        start_y = int(start_y)
        dx = int(dx)
        dy = int(dy)
        thickness = int(thickness)
        outline = int(outline)
        half_thickness = thickness // 2

        if dx != 0:  # 水平线
            x1 = int(min(start_x, start_x + dx))
            x2 = int(max(start_x, start_x + dx))

            # 绘制描边
            if outline > 0:
                y1 = max(0, start_y - half_thickness - outline)
                y2 = min(img.shape[0], start_y + half_thickness + outline)
                x1_out = max(0, x1 - outline)
                x2_out = min(img.shape[1], x2 + outline)
                img[y1:y2, x1_out:x2_out] = outline_color

            # 绘制主线
            y1 = max(0, start_y - half_thickness)
            y2 = min(img.shape[0], start_y + half_thickness)
            x1_clip = max(0, x1)
            x2_clip = min(img.shape[1], x2)
            img[y1:y2, x1_clip:x2_clip] = color

        else:  # 垂直线 (dy != 0)
            y1 = int(min(start_y, start_y + dy))
            y2 = int(max(start_y, start_y + dy))

            # 绘制描边
            if outline > 0:
                x1 = max(0, start_x - half_thickness - outline)
                x2 = min(img.shape[1], start_x + half_thickness + outline)
                y1_out = max(0, y1 - outline)
                y2_out = min(img.shape[0], y2 + outline)
                img[y1_out:y2_out, x1:x2] = outline_color

            # 绘制主线
            x1 = max(0, start_x - half_thickness)
            x2 = min(img.shape[1], start_x + half_thickness)
            y1_clip = max(0, y1)
            y2_clip = min(img.shape[0], y2)
            img[y1_clip:y2_clip, x1:x2] = color

    @staticmethod
    def save(img: np.ndarray, filepath: str = "crosshair.png"):
        """保存图像（确保保留Alpha通道）"""
        if img.shape[2] != 4:
            raise ValueError(f"输入图像必须是4通道BGRA，当前是{img.shape[2]}通道")

        # 转换颜色顺序：OpenCV的BGRA -> PIL的RGBA
        img_rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)

        # 使用PIL保存
        pil_img = Image.fromarray(img_rgba, mode='RGBA')
        pil_img.save(filepath, 'PNG')

        print(f"✅ 准星已保存到: {filepath}")

        # 验证保存结果
        verify = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
        print(f"   验证: {verify.shape[2]}通道, Alpha范围=[{verify[:, :, 3].min()}, {verify[:, :, 3].max()}]")

        return filepath
