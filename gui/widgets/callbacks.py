import dearpygui.dearpygui as dpg
from config import config_manager as cfg
from gui.theme.colors import UIColors

IS_REFRESHING_TARGET_IDS_UI = False


# ============================================================
# 保存按钮回调
# ============================================================

def save_callback():
    """
    保存当前编辑参数组到 profiles.json，
    并同步到全局配置 config.json，使其立即生效。
    """
    edit_profile = cfg.get_edit_profile()
    active_profile = cfg.get_active_profile()

    # 1️⃣ 保存参数组文件
    if not cfg.save_profiles():
        dpg.configure_item(
            "status_text",
            default_value="[错误] 参数组保存失败",
            color=UIColors.ERROR_RED
        )
        return

    # 2️⃣ 始终同步当前编辑组到全局配置
    cfg.sync_profile_to_global(edit_profile)
    cfg.save_config()

    # 3️⃣ 如果编辑组不是运行组，提示用户
    if active_profile != edit_profile:
        dpg.configure_item(
            "status_text",
            default_value=f"[成功] 已保存 {edit_profile} 并同步到全局配置",
            color=UIColors.WARNING_ORANGE
        )
    else:
        dpg.configure_item(
            "status_text",
            default_value=f"[成功] 已保存并应用参数组: {edit_profile}",
            color=UIColors.SUCCESS_GREEN
        )



# ============================================================
# 通用配置更新回调（用于 tagged 控件）
# ============================================================

def update_config_callback(sender, app_data, user_data):
    """
    所有 tagged 控件都会走这里。
    只有 PROFILE_KEYS 中的参数才写入参数组。
    """
    from config.defaults import PROFILE_KEYS  # 导入 PROFILE_KEYS

    key = user_data
    value = app_data
    edit_profile = cfg.get_edit_profile()

    # ✅ 只有在 PROFILE_KEYS 中的参数才写入参数组
    if key in PROFILE_KEYS and edit_profile:
        profile = cfg.get_profile(edit_profile)
        if profile:
            profile.set(key, value)
            dpg.configure_item(
                "status_text",
                default_value=f"[未保存] 已修改({edit_profile}): {key}",
                color=UIColors.WARNING_ORANGE
            )
    else:
        # ✅ 非 PROFILE_KEYS 的参数直接写入全局配置
        cfg.set_config(key, value)
        dpg.configure_item(
            "status_text",
            default_value=f"[未保存] 已修改(全局): {key}",
            color=UIColors.WARNING_ORANGE
        )


# ============================================================
# 目标ID多选回调
# ============================================================

def update_class_ids_callback(sender, app_data, user_data):
    """
    处理 TARGET_CLASS_IDS 多选逻辑。
    只写入当前编辑参数组，不直接同步运行态。
    """

    global IS_REFRESHING_TARGET_IDS_UI

    if IS_REFRESHING_TARGET_IDS_UI:
        return

    target_id = int(user_data)
    is_checked = bool(app_data)

    edit_profile = cfg.get_edit_profile()
    profile = cfg.get_profile(edit_profile)

    if not profile:
        return

    # 1️⃣ 读取当前参数组中的 TARGET_CLASS_IDS
    current_ids = profile.get("TARGET_CLASS_IDS", [])
    if not isinstance(current_ids, list):
        current_ids = []

    # 2️⃣ 更新集合
    s = set(current_ids)
    if is_checked:
        s.add(target_id)
    else:
        s.discard(target_id)

    new_ids = sorted(s)

    # 3️⃣ 写回参数组
    profile.set("TARGET_CLASS_IDS", new_ids)
    dpg.configure_item(
        "status_text",
        default_value=f"[未保存] 已修改({edit_profile}): TARGET_CLASS_IDS = {new_ids}",
        color=UIColors.WARNING_ORANGE
    )
