import dearpygui.dearpygui as dpg
from gui.theme.colors import UIColors


def build_notice_tab(blue_notice_theme):
    with dpg.tab(label=" ", tag="notice_tab", closable=False):
        dpg.add_text("更新公告：", color=UIColors.SECTION_HEADER)
        dpg.add_separator()
        dpg.add_text("• 新增参数组，可实现不同按键触发不同参数", color=UIColors.TEXT_BLACK)
        dpg.add_text("• 网络版本的硬件盒子需要等几天才可以适配，我自己买的网络版还在物流中", color=UIColors.TEXT_BLACK)
        dpg.add_text("• 修复了一些bug", color=UIColors.TEXT_BLACK)
        dpg.add_text("• 部分tab功能发生了变化，可能会产生新的bug", color=UIColors.TEXT_BLACK)
        dpg.add_separator()
        dpg.add_text("更新时间：2026-02-12", color=UIColors.TEXT_BLACK)

    dpg.bind_item_theme("notice_tab", blue_notice_theme)
