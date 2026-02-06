import threading

import dearpygui.dearpygui as dpg

import config_manager as cfg
from tabs.main_window import build_main_window
from theme.apple_theme import (
    setup_apple_theme,
    setup_button_themes,
    setup_notice_tab_theme,
)
from theme.colors import UIColors
from theme.fonts import setup_chinese_font
from widgets.basic import add_float, add_int, add_bool, add_combo
from widgets.callbacks import save_callback, update_config_callback, update_class_ids_callback
from widgets.crosshair_preview import generate_crosshair_preview_callback
from widgets.helpers import update_dependent_controls, create_master_switch_callback
from widgets.preview import update_search_bounds, _handle_preview_drag, update_aim_offset_preview
from widgets.scripts_ui import refresh_scripts_ui
from widgets.tagged import (
    add_float_tagged, add_int_tagged, add_bool_tagged, add_input_text_tagged,
    add_float_input_tagged, add_int_input_tagged, add_combo_tagged
)

# 1. 加载配置
cfg.load_config()

# ========== 全局退出信号 ==========
_gui_exit_event = threading.Event()
_gui_running = False

# ================= 核心控制回调 =================

def update_ai_button_status(is_running):
    """根据运行状态更新按钮颜色和文字"""
    if is_running:
        dpg.configure_item("ai_toggle_btn", label="系统运行中 (点击暂停)")
        dpg.bind_item_theme("ai_toggle_btn", "theme_btn_running")
    else:
        dpg.configure_item("ai_toggle_btn", label="系统已暂停 (点击启动)")
        dpg.bind_item_theme("ai_toggle_btn", "theme_btn_paused")


def toggle_ai_callback(sender, app_data, user_data):
    """启动/暂停 AI"""
    resume_event, _, _ = cfg.get_events()

    if resume_event.is_set():
        # 正在运行 -> 执行暂停
        resume_event.clear()
        update_ai_button_status(False)
        # 可选：同步写入配置，下次启动记住状态
        # cfg.set_config("AI_ENABLED", False)
        print("[GUI] 发送暂停信号")
    else:
        # 暂停中 -> 执行启动
        resume_event.set()
        update_ai_button_status(True)
        # cfg.set_config("AI_ENABLED", True)
        print("[GUI] 发送启动信号")


def manual_reload_callback(sender, app_data, user_data):
    """强制热重载资源"""
    resume_event, reload_event, _ = cfg.get_events()

    print("[GUI] 发送强制重载信号...")
    reload_event.set()

    # 如果当前是暂停状态，必须临时唤醒主线程让它去处理重载
    if not resume_event.is_set():
        resume_event.set()
        # 重载后是否保持暂停，取决于你的业务逻辑，这里默认重载后会让它运行
        update_ai_button_status(True)

# ================= 主 GUI 创建 =================
def create_gui():
    dpg.create_context()
    with dpg.item_handler_registry(tag="preview_handler"):
        # 激活状态（拖动中）
        dpg.add_item_active_handler(callback=_handle_preview_drag)
        # 点击状态（点击即定位）
        dpg.add_item_clicked_handler(callback=_handle_preview_drag)
    # 1. 设置字体
    setup_chinese_font()
    # 2. 应用 Apple 风格主题
    setup_apple_theme()
    setup_button_themes()
    # 注册纹理
    with dpg.texture_registry():
        default_texture = []
        for y in range(90):
            for x in range(90):
                # 浅灰色背景适配白色主题
                default_texture.extend([0.9, 0.9, 0.9, 1.0])

        dpg.add_dynamic_texture(
            width=90,
            height=90,
            default_value=default_texture,
            tag="crosshair_preview_texture"
        )

    blue_notice_theme = setup_notice_tab_theme()
    with dpg.window(tag="Primary Window", label="test-v1.0"):

        # === 顶部状态栏 ===
        with dpg.group(horizontal=True):
            # dpg.add_text("--", color=UIColors.APPLE_BLUE)
            dpg.add_button(
                tag="ai_toggle_btn",
                label="初始化中...",
                callback=toggle_ai_callback,
                width=160,
                height=30
            )
            # [核心功能] 强制重载 按钮
            dpg.add_button(
                label="重载配置/模型",
                callback=manual_reload_callback,
                height=30
            )
            # 保存按钮
            dpg.add_button(label="保存所有配置 (Save)", callback=save_callback, height=30, width=160)
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("修改参数后必须点击此处才可以生效,\n如果不点击保存直接点击重启参数修改会丢失.")
            dpg.add_text("[就绪]", tag="status_text", color=UIColors.TEXT_GRAY)

        dpg.add_separator()

        with dpg.tab_bar():
            build_main_window(blue_notice_theme)




    dpg.create_viewport(title="Prism Vision-v1.3", width=900, height=800)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    update_aim_offset_preview()
    dpg.set_primary_window("Primary Window", True)
    refresh_scripts_ui()
    global _gui_running
    _gui_running = True

    resume_event, _, _ = cfg.get_events()
    update_ai_button_status(resume_event.is_set())
    last_running_state = None
    try:
        while dpg.is_dearpygui_running():
            if _gui_exit_event.is_set():
                print("[GUI] 收到退出信号，准备关闭...")
                dpg.stop_dearpygui()
                break
            # ========== 🔥 修复：实时状态同步 ==========
            # 获取当前真实的运行状态
            current_running_state = resume_event.is_set()

            # 如果真实状态和记录的状态不一致（比如被 ConfigManager 自动开启了）
            if current_running_state != last_running_state:
                update_ai_button_status(current_running_state)
                last_running_state = current_running_state
            # =========================================

            dpg.render_dearpygui_frame()
    finally:
        dpg.destroy_context()
        _gui_running = False
        print("[GUI] ✅ GUI 已完全清理")
# ================= 外部控制函数 =================
def stop_gui():
    print("[GUI] 正在请求 GUI 退出...")
    _gui_exit_event.set()
def is_gui_running():
    return _gui_running
if __name__ == "__main__":
    create_gui()
