import dearpygui.dearpygui as dpg
from gui.theme.colors import UIColors

from gui.widgets.basic import add_int

from gui.widgets.tagged import add_int_tagged, add_bool_tagged

from gui.widgets.helpers import create_master_switch_callback
from config import config_manager as cfg
from gui.widgets.helpers import update_dependent_controls
from gui.widgets.tagged import add_input_text_tagged, add_float_input_tagged, add_int_input_tagged


def build_driver_keys_tab(blue_notice_theme):
    with dpg.tab(label="驱动模式"):
        dpg.add_text("硬件模式选择", color=UIColors.APPLE_BLUE)
        dpg.add_text(r"Makcu\MTKmbox\传统驱动只能选一个", color=UIColors.ERROR_RED)

        # ========== Makcu 硬件模式 ==========
        dpg.add_separator()
        dpg.add_text("Makcu 硬件模式", color=UIColors.SECTION_HEADER)

        makcu_deps = ["makcu_port", "makcu_reconnect", "makcu_interval", "makcu_queue",
                      "makcu_hw_monitor", "makcu_fallback"]
        makcu_enabled = cfg.get_config("USE_MAKCU", False)
        dpg.add_checkbox(
            label="启用 Makcu 硬件",
            default_value=makcu_enabled,
            callback=create_master_switch_callback("USE_MAKCU", makcu_deps)
        )

        add_input_text_tagged("MAKCU_PORT", "Makcu COM口 (留空自动搜索)", "makcu_port")
        add_bool_tagged("MAKCU_AUTO_RECONNECT", "Makcu 断线自动重连", "makcu_reconnect")

        add_float_input_tagged("MAKCU_MIN_SEND_INTERVAL", "发送间隔 (秒)", "makcu_interval")
        with dpg.tooltip("makcu_interval"):
            dpg.add_text("串口写入的最小时间间隔\n如果出现 Write Timeout 或卡顿，请调大此值")

        add_int_input_tagged("MAKCU_QUEUE_SIZE", "指令队列缓冲", "makcu_queue")

        add_bool_tagged("MAKCU_USE_HARDWARE_MONITOR", "使用硬件按键监控", "makcu_hw_monitor")
        add_bool_tagged("MAKCU_FALLBACK_TO_PYNPUT", "监控失败时回退到软件", "makcu_fallback")

        update_dependent_controls("USE_MAKCU", makcu_deps, makcu_enabled)

        # ========== MTKmbox 硬件模式 ==========
        dpg.add_separator()
        dpg.add_text("MTKmbox 硬件模式", color=UIColors.SECTION_HEADER)

        mtk_deps = ["mtk_port", "mtk_vid", "mtk_pid", "mtk_max_move",
                    "mtk_hw_monitor", "mtk_fallback", "mtk_debug"]
        mtk_enabled = cfg.get_config("USE_MTKMBOX", False)
        dpg.add_checkbox(
            label="启用 MTKmbox 硬件 (与Makcu/驱动互斥)",
            default_value=mtk_enabled,
            callback=create_master_switch_callback("USE_MTKMBOX", mtk_deps)
        )

        add_input_text_tagged("MTKMBOX_PORT", "MTKmbox COM口", "mtk_port")

        add_int_input_tagged("MTKMBOX_VID", "USB VID (十进制)", "mtk_vid")
        with dpg.tooltip("mtk_vid"):
            dpg.add_text("设备 Vendor ID，默认 1046 (0x0416)")

        add_int_input_tagged("MTKMBOX_PID", "USB PID (十进制)", "mtk_pid")
        with dpg.tooltip("mtk_pid"):
            dpg.add_text("设备 Product ID，默认 20512 (0x5020)")

        add_int_input_tagged("MTKMBOX_MAX_MOVE", "单次最大移动量", "mtk_max_move")
        with dpg.tooltip("mtk_max_move"):
            dpg.add_text("MTKmbox 单次移动的最大像素值\n协议限制：1-127")

        add_bool_tagged("MTKMBOX_USE_HARDWARE_MONITOR", "使用硬件按键监控", "mtk_hw_monitor")
        add_bool_tagged("MTKMBOX_FALLBACK_TO_PYNPUT", "监控失败时回退到软件", "mtk_fallback")
        add_bool_tagged("MTKMBOX_DEBUG_MODE", "MTKmbox 调试模式", "mtk_debug")

        update_dependent_controls("USE_MTKMBOX", mtk_deps, mtk_enabled)

        # ========== 传统驱动模式 ==========
        dpg.add_separator()
        dpg.add_text("传统驱动模式", color=UIColors.SECTION_HEADER)

        driver_deps = ["driver_fallback", "driver_path", "driver_request", "driver_mickey"]
        driver_enabled = cfg.get_config("USE_DRIVER_MODE", False)
        dpg.add_checkbox(
            label="使用传统硬件驱动 (与Makcu/MTKmbox互斥)",
            default_value=driver_enabled,
            callback=create_master_switch_callback("USE_DRIVER_MODE", driver_deps)
        )

        add_bool_tagged("MOUSE_MODE_AUTO_FALLBACK", "驱动失败自动回退", "driver_fallback")
        add_input_text_tagged("DRIVER_PATH", "驱动设备路径", "driver_path")
        add_int_tagged("MOUSE_REQUEST", "鼠标 Request Code", 0, 9999999, "driver_request")
        add_int_tagged("MAX_MICKEY", "鼠标移动量限制 (Mickey)", 100, 5000, "driver_mickey")

        update_dependent_controls("USE_DRIVER_MODE", driver_deps, driver_enabled)

        # ========== 通用串口配置 ==========
        dpg.add_separator()
        dpg.add_text("通用串口配置", color=UIColors.TEXT_GRAY)

        add_float_input_tagged("SERIAL_MIN_SEND_INTERVAL", "串口最小发送间隔 (秒)", "serial_interval")
        with dpg.tooltip("serial_interval"):
            dpg.add_text("适用于所有串口设备 (Makcu/MTKmbox)\n如果出现通信超时，请调大此值")


        # ========== 按键映射 ID ==========
        dpg.add_separator()
        dpg.add_text("按键映射 ID (高级选项，谨慎修改)", color=UIColors.TEXT_GRAY)

        add_int("APP_MOUSE_LEFT_DOWN", "Left Down ID", 0, 100)
        add_int("APP_MOUSE_LEFT_UP", "Left Up ID", 0, 100)
        add_int("APP_MOUSE_RIGHT_DOWN", "Right Down ID", 0, 100)
        add_int("APP_MOUSE_RIGHT_UP", "Right Up ID", 0, 100)