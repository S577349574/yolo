import dearpygui.dearpygui as dpg
from gui.theme.colors import UIColors


from gui.widgets.tagged import add_int_tagged, add_bool_tagged

from gui.widgets.helpers import create_master_switch_callback
from config import config_manager as cfg


def build_preview_tab(blue_notice_theme):
    with dpg.tab(label="预览窗口"):
        dpg.add_text("窗口基础设置", color=UIColors.APPLE_BLUE)

        preview_deps = [
            "preview_width", "preview_height", "preview_skip",
            "preview_show_boxes", "preview_show_labels", "preview_show_conf",
            "preview_show_fps", "preview_show_cross", "preview_show_aim",
            "preview_box_thick", "preview_text_scale"
        ]
        preview_enabled = cfg.get_config("ENABLE_PREVIEW_WINDOW", False)
        dpg.add_checkbox(
            label="启用预览窗口",
            default_value=preview_enabled,
            callback=create_master_switch_callback("ENABLE_PREVIEW_WINDOW", preview_deps)
        )

        add_int_tagged("PREVIEW_WINDOW_WIDTH", "窗口宽度", 400, 1920, "preview_width")
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("尺寸可以不和onnx模型一样，可以自定义大小\n"
                         )

        add_int_tagged("PREVIEW_WINDOW_HEIGHT", "窗口高度", 400, 1080, "preview_height")
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("尺寸可以不和onnx模型一样，可以自定义大小\n"
                         )
        add_int_tagged("PREVIEW_FRAME_SKIP", "跳帧数 (0=不跳帧)", 0, 10, "preview_skip")
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("设置0就是在预览窗口显示所有的截图，设置1就是2张截图只显示1张。\n"
                         "比如，你的fps是120，如果设置1，预览窗口就变成60fps\n"
                         "此预览窗口是异步画面，不影响程序性能，也不会造成真是推理帧数降低。\n"
                         )

        dpg.add_separator()
        dpg.add_text("显示选项", color=UIColors.SECTION_HEADER)
        add_bool_tagged("PREVIEW_SHOW_BOXES", "显示检测框", "preview_show_boxes")
        add_bool_tagged("PREVIEW_SHOW_LABELS", "显示类别标签", "preview_show_labels")
        add_bool_tagged("PREVIEW_SHOW_CONFIDENCE", "显示置信度", "preview_show_conf")
        add_bool_tagged("PREVIEW_SHOW_FPS", "显示 FPS 信息", "preview_show_fps")
        add_bool_tagged("PREVIEW_SHOW_CROSSHAIR", "显示准心十字线", "preview_show_cross")
        add_bool_tagged("PREVIEW_SHOW_AIM_POINT", "显示瞄准点", "preview_show_aim")
        add_bool_tagged("PREVIEW_SHOW_SEARCH_AREA", "显示准星搜索区域", "preview_show_search")

        dpg.add_separator()
        dpg.add_text("视觉样式", color=UIColors.SECTION_HEADER)
        add_int_tagged("PREVIEW_BOX_THICKNESS", "检测框线宽", 1, 5, "preview_box_thick")