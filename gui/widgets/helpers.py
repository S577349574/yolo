import dearpygui.dearpygui as dpg

from config import config_manager as cfg
from gui.theme.colors import UIColors


def update_dependent_controls(master_key, dependent_tags, is_enabled):
    """通用函数：根据主开关状态启用/禁用子控件"""
    for tag in dependent_tags:
        try:
            dpg.configure_item(tag, enabled=is_enabled)
        except Exception as e:
            print(f"[GUI] 无法更新控件 {tag}: {e}")


def create_master_switch_callback(config_key, dependent_tags):
    """创建带联动的主开关回调函数"""

    def callback(sender, app_data, user_data):
        cfg.set_config(config_key, app_data)
        dpg.configure_item(
            "status_text",
            default_value=f"[未保存] 已修改: {config_key}",
            color=UIColors.WARNING_ORANGE
        )
        update_dependent_controls(config_key, dependent_tags, app_data)

    return callback
