import dearpygui.dearpygui as dpg
from gui.theme.colors import UIColors

from gui.widgets.basic import add_combo, add_int


def build_image_source_tab(blue_notice_theme):
    with dpg.tab(label="图像源"):
        dpg.add_text("画面来源模式(需要重启启动)", color=UIColors.APPLE_BLUE)
        add_combo("IMAGE_SOURCE_TYPE", "图像源类型", ["local", "network"])
        add_int("CROP_SIZE", "推理区域大小 (Crop)", 64, 1280)
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("在v1.2版本以后，此参数可以忽略，程序将优先从onnx模型文件中提取需要的截图尺寸。\n"
                         "此参数在v1.2以后为兜底参数可以不调整\n"
                         )
        dpg.add_separator()
        dpg.add_text("网络画面接收配置(需要重启启动) (仅network模式生效)", color=UIColors.SECTION_HEADER)
        add_int("FRAME_PORT", "接收端口", 1024, 65535)
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("填写游戏机agent配置中的FRAME_PORT参数\n"
                         "图片来源选择网络，游戏机和推理机必须在一个局域网环境下才可以\n"
                         )
        add_int("FRAME_WIDTH", "画面宽度 (像素)", 64, 1920)
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("填写游戏机agent配置中的width参数\n"
                         "此参数要和onnx模型尺寸同步\n"
                         )
        add_int("FRAME_HEIGHT", "画面高度 (像素)", 64, 1080)
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("填写游戏机agent配置中的height参数\n"
                         "此参数要和onnx模型尺寸同步\n"
                         )
        add_int("FRAME_CHANNELS", "通道数 (RGB=3, RGBA=4)", 3, 4)