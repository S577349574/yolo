# gui1.py
import threading
import time
import ctypes
import ctypes.wintypes

import dearpygui.dearpygui as dpg

import config_manager as cfg
from gui.tabs.main_window import build_main_window
from gui.theme.apple_theme import (
    setup_apple_theme,
    setup_button_themes,
    setup_notice_tab_theme,
)
from gui.theme.colors import UIColors
from gui.theme.fonts import setup_chinese_font
from gui.widgets.callbacks import save_callback
from gui.widgets.preview import _handle_preview_drag, update_aim_offset_preview
from gui.widgets.scripts_ui import refresh_scripts_ui

# 1. 加载配置
cfg.load_config()

# ========== 全局退出信号 ==========
_gui_exit_event = threading.Event()
_gui_running = False

# UI 焦点状态管理
_ui_has_focus = True
_focus_monitor_thread = None

# ================= Windows API 声明 =================
user32 = ctypes.windll.user32
GetForegroundWindow = user32.GetForegroundWindow
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
GetCurrentProcessId = ctypes.windll.kernel32.GetCurrentProcessId


def is_gui_window_active():
    """检测当前活动窗口是否是本程序的 GUI 窗口"""
    try:
        foreground_hwnd = GetForegroundWindow()
        if not foreground_hwnd:
            return False

        foreground_pid = ctypes.wintypes.DWORD()
        GetWindowThreadProcessId(foreground_hwnd, ctypes.byref(foreground_pid))

        current_pid = GetCurrentProcessId()
        return foreground_pid.value == current_pid
    except Exception:
        return False


# ================= UI 焦点检测 =================

def on_ui_focus_gained():
    """UI 获得焦点时（用户开始操作 UI）"""
    global _ui_has_focus
    if not _ui_has_focus:
        _ui_has_focus = True
        try:
            key_monitor = cfg.get_key_monitor()
            if key_monitor and hasattr(key_monitor, 'set_ui_focus_mode'):
                key_monitor.set_ui_focus_mode(True)
        except Exception as e:
            print(f"[GUI] 焦点检测警告: {e}")


def on_ui_focus_lost():
    """UI 失去焦点时（用户回到游戏）"""
    global _ui_has_focus
    if _ui_has_focus:
        _ui_has_focus = False
        try:
            key_monitor = cfg.get_key_monitor()
            if key_monitor and hasattr(key_monitor, 'set_ui_focus_mode'):
                key_monitor.set_ui_focus_mode(False)
        except Exception as e:
            print(f"[GUI] 焦点检测警告: {e}")


def focus_monitor_worker():
    """后台线程：实时监控窗口焦点状态"""
    max_wait = 10.0
    start_time = time.time()
    key_monitor = None

    # 等待 KeyMonitor 初始化
    while _gui_running and not _gui_exit_event.is_set():
        key_monitor = cfg.get_key_monitor()
        if key_monitor is not None:
            if hasattr(key_monitor, 'is_running') and key_monitor.is_running():
                break
            elif hasattr(key_monitor, '_is_running') and key_monitor._is_running:
                break

        if time.time() - start_time > max_wait:
            print("[GUI] ⚠ KeyMonitor 初始化超时")
            break

        time.sleep(0.2)

    # 设置初始焦点状态
    if _gui_running and not _gui_exit_event.is_set() and key_monitor is not None:
        global _ui_has_focus
        _ui_has_focus = True

        for attempt in range(3):
            try:
                if hasattr(key_monitor, 'set_ui_focus_mode'):
                    key_monitor.set_ui_focus_mode(True)
                    break
                else:
                    print("[GUI] ⚠ KeyMonitor 缺少 set_ui_focus_mode 方法")
                    break
            except Exception as e:
                if attempt == 2:  # 只在最后一次失败时打印
                    print(f"[GUI] ⚠ 设置焦点模式失败: {e}")
                time.sleep(0.3)

    # 监控循环
    while _gui_running and not _gui_exit_event.is_set():
        try:
            gui_is_active = is_gui_window_active()

            if gui_is_active and not _ui_has_focus:
                on_ui_focus_gained()
            elif not gui_is_active and _ui_has_focus:
                on_ui_focus_lost()

        except Exception as e:
            print(f"[GUI] 焦点监控异常: {e}")

        time.sleep(0.2)


def start_focus_monitor():
    """启动焦点监控线程"""
    global _focus_monitor_thread

    if _focus_monitor_thread and _focus_monitor_thread.is_alive():
        return

    _focus_monitor_thread = threading.Thread(
        target=focus_monitor_worker,
        daemon=True,
        name="FocusMonitorThread"
    )
    _focus_monitor_thread.start()


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
        resume_event.clear()
        update_ai_button_status(False)
    else:
        resume_event.set()
        update_ai_button_status(True)


def manual_reload_callback(sender, app_data, user_data):
    """强制热重载资源"""
    resume_event, reload_event, _ = cfg.get_events()
    reload_event.set()

    if not resume_event.is_set():
        resume_event.set()
        update_ai_button_status(True)


# ================= 主 GUI 创建 =================
def create_gui():
    dpg.create_context()
    with dpg.item_handler_registry(tag="preview_handler"):
        dpg.add_item_active_handler(callback=_handle_preview_drag)
        dpg.add_item_clicked_handler(callback=_handle_preview_drag)

    setup_chinese_font()
    setup_apple_theme()
    setup_button_themes()

    with dpg.texture_registry():
        default_texture = []
        for y in range(90):
            for x in range(90):
                default_texture.extend([0.9, 0.9, 0.9, 1.0])

        dpg.add_dynamic_texture(
            width=90,
            height=90,
            default_value=default_texture,
            tag="crosshair_preview_texture"
        )

    blue_notice_theme = setup_notice_tab_theme()
    with dpg.window(tag="Primary Window", label="test-v1.0"):

        with dpg.group(horizontal=True):
            dpg.add_text("--C总", color=UIColors.APPLE_BLUE)
            dpg.add_button(
                tag="ai_toggle_btn",
                label="初始化中...",
                callback=toggle_ai_callback,
                width=160,
                height=30
            )
            dpg.add_button(
                label="重载配置/模型",
                callback=manual_reload_callback,
                height=30
            )
            dpg.add_button(label="保存所有配置 (Save)", callback=save_callback, height=30, width=160)
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("修改参数后必须点击此处才可以生效,\n如果不点击保存直接点击重启参数修改会丢失.")
            dpg.add_text("[就绪]", tag="status_text", color=UIColors.TEXT_GRAY)

        dpg.add_separator()

        with dpg.tab_bar():
            build_main_window(blue_notice_theme)

    dpg.create_viewport(title="Prism Vision-v1.4(Beta)", width=900, height=800)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    update_aim_offset_preview()
    dpg.set_primary_window("Primary Window", True)
    refresh_scripts_ui()

    global _gui_running
    _gui_running = True

    start_focus_monitor()

    resume_event, _, _ = cfg.get_events()
    update_ai_button_status(resume_event.is_set())
    last_running_state = None

    try:
        while dpg.is_dearpygui_running():
            if _gui_exit_event.is_set():
                dpg.stop_dearpygui()
                break

            current_running_state = resume_event.is_set()
            if current_running_state != last_running_state:
                update_ai_button_status(current_running_state)
                last_running_state = current_running_state

            dpg.render_dearpygui_frame()
    finally:
        on_ui_focus_lost()

        if _focus_monitor_thread and _focus_monitor_thread.is_alive():
            _focus_monitor_thread.join(timeout=1.0)

        dpg.destroy_context()
        _gui_running = False


# ================= 外部控制函数 =================
def stop_gui():
    _gui_exit_event.set()


def is_gui_running():
    return _gui_running


if __name__ == "__main__":
    create_gui()
