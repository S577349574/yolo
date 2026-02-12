import dearpygui.dearpygui as dpg

from gui.theme.colors import UIColors
from gui.widgets.basic import add_bool
from gui.widgets.basic import add_int
from gui.widgets.scripts_ui import refresh_scripts_ui


def build_scripts_tab(blue_notice_theme):
    # ================= TAB 11: 脚本扩展 =================
    with dpg.tab(label="脚本扩展"):
        dpg.add_text("脚本执行设置", color=UIColors.APPLE_BLUE)
        add_bool("ENABLE_SCRIPT_SYSTEM", "是否开启脚本功能")
        add_bool("SCRIPT_AUTO_RELOAD", "脚本自动重载 (监听文件修改)")
        add_bool("SCRIPT_DEBUG_MODE", "脚本调试模式 (输出详细日志)")
        add_int("SCRIPT_TIMEOUT_MS", "脚本执行超时 (ms)", 1, 1000)

        dpg.add_separator()

        with dpg.group(horizontal=True):
            dpg.add_text("可用脚本列表", color=UIColors.SECTION_HEADER)
            dpg.add_button(label="刷新列表", callback=refresh_scripts_ui, small=True)

        dpg.add_text("勾选以启用脚本 (自动保存至配置)", color=UIColors.TEXT_GRAY)

        # === 脚本列表容器 ===
        dpg.add_group(tag="script_list_container")