import dearpygui.dearpygui as dpg
from theme.colors import UIColors


def build_notice_tab(blue_notice_theme):
    with dpg.tab(label=" ", tag="notice_tab", closable=False):
        dpg.add_text("更新公告：", color=UIColors.SECTION_HEADER)
        dpg.add_separator()
        dpg.add_text("• 这是第一条公告内容", color=UIColors.TEXT_BLACK)
        dpg.add_text("• 这是第二条公告内容", color=UIColors.TEXT_BLACK)
        dpg.add_separator()
        dpg.add_text("更新时间：2024-01-01", color=UIColors.TEXT_BLACK)

    dpg.bind_item_theme("notice_tab", blue_notice_theme)
