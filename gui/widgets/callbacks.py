import dearpygui.dearpygui as dpg

import config_manager as cfg
from gui.theme.colors import UIColors
IS_REFRESHING_TARGET_IDS_UI = False


# 注意：为避免循环，这里用“局部导入”或在文件底部导入都可以。
# 我们在函数内部导入，最稳。


# gui1.py 中的 save_callback 示例

def save_callback():
    active_profile = cfg.get_active_profile()

    if not cfg.save_profiles():
        dpg.configure_item(
            "status_text",
            default_value="[错误] 参数组保存失败",
            color=UIColors.ERROR_RED
        )
        return

    # 可选：保存运行态配置
    cfg.save_config()

    dpg.configure_item(
        "status_text",
        default_value=f"[成功] 已保存参数组: {active_profile}",
        color=UIColors.SUCCESS_GREEN
    )

    # 保存参数组配置（通过 cfg.save_profiles 调用）
    success = cfg.save_profiles()  # 调用保存参数组配置的方法
    if success:
        dpg.configure_item(
            "status_text",
            default_value="[成功] 参数组配置已保存至 profiles.json",
            color=UIColors.SUCCESS_GREEN
        )
    else:
        dpg.configure_item(
            "status_text",
            default_value="[错误] 参数组保存失败！",
            color=UIColors.ERROR_RED
        )


def update_config_callback(sender, app_data, user_data):
    key = user_data
    value = app_data

    active_profile = cfg.get_active_profile()

    if active_profile:
        # ✅ 写入参数组
        profile = cfg.get_profile(active_profile) if active_profile else None
        if profile:
            profile.set(key, value)

    # ✅ 同时更新全局配置（让运行中的系统生效）
    cfg.set_config(key, value)

    dpg.configure_item(
        "status_text",
        default_value=f"[未保存] 已修改({active_profile}): {key}",
        color=UIColors.WARNING_ORANGE
    )



def update_class_ids_callback(sender, app_data, user_data):
    if IS_REFRESHING_TARGET_IDS_UI:
        return
    """处理目标ID多选（写入当前参数组 + 同步运行配置）"""
    target_id = int(user_data)
    is_checked = bool(app_data)

    active_profile = cfg.get_active_profile()

    # 1) 先从“当前参数组”取值（优先保证写入 profile 的正确性）
    current_ids = []
    if active_profile:
        profile = cfg.get_profile(active_profile)
        if isinstance(profile, dict):
            current_ids = profile.get("TARGET_CLASS_IDS", [])
        else:
            # 如果你们的 profile 是自定义对象（有 get/set），就用它的 get
            try:
                current_ids = profile.get("TARGET_CLASS_IDS", [])
            except Exception:
                current_ids = []

    # 兜底：如果 profile 里没有，就从全局取
    if not isinstance(current_ids, list):
        current_ids = cfg.get_config("TARGET_CLASS_IDS", [])
    if not isinstance(current_ids, list):
        current_ids = []

    # 2) 更新列表
    s = set(current_ids)
    if is_checked:
        s.add(target_id)
    else:
        s.discard(target_id)

    new_ids = sorted(s)

    # 3) ✅ 写入当前参数组（profiles.json 才会保存到对应组）
    if active_profile:
        profile = cfg.get_profile(active_profile)
        if profile:
            # dict 或对象两种都兼容
            if isinstance(profile, dict):
                profile["TARGET_CLASS_IDS"] = new_ids
            else:
                profile.set("TARGET_CLASS_IDS", new_ids)

    # 4) ✅ 同步运行态全局配置（让系统立即生效）
    cfg.set_config("TARGET_CLASS_IDS", new_ids)

    dpg.configure_item(
        "status_text",
        default_value=f"[未保存] 已修改({active_profile}): TARGET_CLASS_IDS = {new_ids}",
        color=UIColors.WARNING_ORANGE
    )

