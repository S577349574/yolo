import dearpygui.dearpygui as dpg
# gui/theme/apple_theme.py

import dearpygui.dearpygui as dpg

from gui.gui import UIColors


def setup_apple_theme():
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            # ===== 圆角 & 间距 =====
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 10, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 8, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 6, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 6, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize, 12, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, 12, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 10, 8, category=dpg.mvThemeCat_Core)

            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 1, category=dpg.mvThemeCat_Core)

            # ===== 背景 =====
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (255, 255, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (245, 245, 247), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg, (255, 255, 255), category=dpg.mvThemeCat_Core)

            # ===== Header / 下拉 =====
            dpg.add_theme_color(dpg.mvThemeCol_Header, (242, 242, 247), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (229, 229, 234), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (209, 209, 214), category=dpg.mvThemeCat_Core)

            # ===== 文字 =====
            dpg.add_theme_color(dpg.mvThemeCol_Text, (28, 28, 30), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, (142, 142, 147), category=dpg.mvThemeCat_Core)

            # ===== 边框 =====
            dpg.add_theme_color(dpg.mvThemeCol_Border, (200, 200, 200), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_BorderShadow, (0, 0, 0, 0), category=dpg.mvThemeCat_Core)

            # ===== 按钮 =====
            dpg.add_theme_color(dpg.mvThemeCol_Button, (242, 242, 247), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (229, 229, 234), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (209, 209, 214), category=dpg.mvThemeCat_Core)

            # ===== 输入框 =====
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (255, 255, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (250, 250, 250), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (235, 235, 240), category=dpg.mvThemeCat_Core)

            # ===== Slider / Checkbox =====
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (0, 122, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (0, 122, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (0, 99, 209), category=dpg.mvThemeCat_Core)

            # ===== Tabs =====
            dpg.add_theme_color(dpg.mvThemeCol_Tab, (242, 242, 247), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (250, 250, 250), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_TabActive, (215, 230, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_TabUnfocusedActive, (230, 240, 255), category=dpg.mvThemeCat_Core)

            # ===== Scrollbar =====
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, (255, 255, 255, 0), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, (199, 199, 204), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, (174, 174, 178), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, (142, 142, 147), category=dpg.mvThemeCat_Core)

    dpg.bind_theme(global_theme)

def setup_button_themes():
    # 运行中（绿色）
    with dpg.theme(tag="theme_btn_running"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (46, 125, 50))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (56, 142, 60))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (27, 94, 32))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255))

    # 暂停（红色）
    with dpg.theme(tag="theme_btn_paused"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (198, 40, 40))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (211, 47, 47))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (183, 28, 28))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255))

def setup_notice_tab_theme():
    with dpg.theme() as blue_notice_theme:
        with dpg.theme_component(dpg.mvTab):
            dpg.add_theme_color(dpg.mvThemeCol_Tab, (0, 122, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (30, 140, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TabActive, (0, 100, 220))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255))

    return blue_notice_theme

def create_table_header_theme():
    with dpg.theme() as table_theme:
        with dpg.theme_component(dpg.mvTable):
            # 表头默认背景色(未选中状态) - 关键!
            dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg, (229, 229, 234))
            # 表头激活/选中色
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (70, 130, 220))
    return table_theme
