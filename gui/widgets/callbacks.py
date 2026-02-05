import dearpygui.dearpygui as dpg

import config_manager as cfg
from theme.colors import UIColors


# 注意：为避免循环，这里用“局部导入”或在文件底部导入都可以。
# 我们在函数内部导入，最稳。


def save_callback():
    """保存配置"""
    if cfg.save_config():
        dpg.configure_item(
            "status_text",
            default_value="[成功] 配置已保存至 config.json",
            color=UIColors.SUCCESS_GREEN
        )
    else:
        dpg.configure_item(
            "status_text",
            default_value="[错误] 保存失败！请检查权限",
            color=UIColors.ERROR_RED
        )


def update_config_callback(sender, app_data, user_data):
    """通用单值更新回调"""
    key = user_data
    value = app_data
    cfg.set_config(key, value)

    dpg.configure_item(
        "status_text",
        default_value=f"[未保存] 已修改: {key}",
        color=UIColors.WARNING_ORANGE
    )

    if key in ["AIM_X_OFFSET", "AIM_Y_RATIO"]:
        # 延迟导入，避免循环依赖
        from widgets.preview import update_aim_offset_preview
        update_aim_offset_preview()


def update_class_ids_callback(sender, app_data, user_data):
    """处理目标ID多选"""
    target_id = user_data
    is_checked = app_data

    current_ids = cfg.get_config("TARGET_CLASS_IDS", [])
    if not isinstance(current_ids, list):
        current_ids = []

    if is_checked:
        if target_id not in current_ids:
            current_ids.append(target_id)
    else:
        if target_id in current_ids:
            current_ids.remove(target_id)

    current_ids.sort()
    cfg.set_config("TARGET_CLASS_IDS", current_ids)

    dpg.configure_item(
        "status_text",
        default_value=f"[未保存] 目标ID更新: {current_ids}",
        color=UIColors.WARNING_ORANGE
    )
