import cv2
import dearpygui.dearpygui as dpg
import numpy as np

import config_manager as cfg
from gui.theme.colors import UIColors


def generate_crosshair_preview_callback(sender, app_data, user_data):
    try:
        config_code = cfg.get_config("CROSSHAIR_VALORANT_CONFIG", "").strip()

        if not config_code:
            dpg.configure_item("status_text", default_value="[错误] 请先填写准星代码", color=UIColors.ERROR_RED)
            return

        dpg.configure_item("status_text", default_value="[处理中] 正在生成...", color=UIColors.WARNING_ORANGE)

        from crosshair.games.valorant.config_parser import ValorantConfigParser
        from crosshair.games.valorant.crosshair_visualizer import CrosshairVisualizer

        config = ValorantConfigParser.parse(config_code)
        desc = ValorantConfigParser.describe(config)

        template_img = CrosshairVisualizer.render(config, size=90)
        img_rgba = cv2.cvtColor(template_img, cv2.COLOR_BGRA2RGBA)

        alpha = img_rgba[:, :, 3:4].astype(np.float32) / 255.0
        rgb = img_rgba[:, :, :3].astype(np.float32)

        background = np.full((90, 90, 3), 230, dtype=np.float32)
        blended_rgb = rgb * alpha + background * (1 - alpha)

        final_rgba = np.concatenate([
            blended_rgb.astype(np.uint8),
            np.full((90, 90, 1), 255, dtype=np.uint8)
        ], axis=-1)

        texture_data = (final_rgba.astype(np.float32) / 255.0).flatten().tolist()
        dpg.set_value("crosshair_preview_texture", texture_data)

        dpg.configure_item("crosshair_preview_desc", default_value=f"✅ {desc}", color=UIColors.SUCCESS_GREEN)
        dpg.configure_item("status_text", default_value="[成功] 准星预览已生成", color=UIColors.SUCCESS_GREEN)

    except ValueError as e:
        dpg.configure_item("crosshair_preview_desc", default_value="❌ 准星代码格式错误", color=UIColors.ERROR_RED)
        dpg.configure_item("status_text", default_value=f"[错误] 准星代码格式错误: {str(e)}", color=UIColors.ERROR_RED)

    except Exception as e:
        dpg.configure_item("crosshair_preview_desc", default_value="❌ 生成失败", color=UIColors.ERROR_RED)
        dpg.configure_item("status_text", default_value=f"[错误] {str(e)}", color=UIColors.ERROR_RED)
        import traceback
        traceback.print_exc()
