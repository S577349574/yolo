import dearpygui.dearpygui as dpg
from config import config_manager as cfg

from gui.widgets.callbacks import update_config_callback


# ============================================================
# 内部映射（用于批量刷新）
# ============================================================

_TAGGED_KEY_TO_TAG = {}
_TAGGED_TAG_TO_KEY = {}


def _register_tagged(key: str, tag: str | None):
    """记录 key <-> tag 的映射"""
    if not tag:
        return
    _TAGGED_KEY_TO_TAG[key] = tag
    _TAGGED_TAG_TO_KEY[tag] = key


# ============================================================
# 刷新函数（当 UI 切换 edit_profile 时调用）
# ============================================================

def refresh_all_tagged_controls():
    """从当前编辑参数组刷新 UI（带类型安全保护）"""
    profile_name = cfg.get_edit_profile()
    profile = cfg.get_profile(profile_name)
    if not profile:
        return

    for key, tag in _TAGGED_KEY_TO_TAG.items():
        if not dpg.does_item_exist(tag):
            continue

        try:
            # ✅ 根据 key 是否在 PROFILE_KEYS 中选择配置源
            if key in PROFILE_KEYS:
                value = profile.get(key)
            else:
                value = cfg.get_config(key)

            # 防止 None
            if value is None:
                continue

            item_type = dpg.get_item_type(tag)

            # 复选框
            if "Checkbox" in item_type:
                dpg.set_value(tag, bool(value))

            # 整数输入
            elif "Int" in item_type:
                dpg.set_value(tag, int(value))

            # 浮点输入
            elif "Float" in item_type:
                dpg.set_value(tag, float(value))

            # Combo
            elif "Combo" in item_type:
                items = dpg.get_item_configuration(tag).get("items", [])
                if value not in items:
                    items.append(value)
                    dpg.configure_item(tag, items=items)
                dpg.set_value(tag, value)

            else:
                dpg.set_value(tag, value)

        except Exception as e:
            print(f"[GUI] 刷新控件失败 key={key} tag={tag}: {e}")




# ============================================================
# 各种 tagged 控件
# ============================================================

def add_float_tagged(key, label, min_v=0.0, max_v=1.0, tag=None, speed=0.01):
    _register_tagged(key, tag)

    if key in PROFILE_KEYS:
        edit_profile = cfg.get_edit_profile()
        profile = cfg.get_profile(edit_profile)
        val = float(profile.get(key, 0.0)) if profile else 0.0
    else:
        val = float(cfg.get_config(key, 0.0))

    dpg.add_drag_float(
        label=label,
        default_value=val,
        min_value=min_v,
        max_value=max_v,
        speed=speed,
        callback=update_config_callback,
        user_data=key,
        width=280,
        tag=tag
    )


from config.defaults import PROFILE_KEYS  # 在文件顶部导入

def add_int_tagged(key, label, min_v=0, max_v=100, tag=None):
    _register_tagged(key, tag)

    # ✅ 根据 key 是否在 PROFILE_KEYS 中选择配置源
    if key in PROFILE_KEYS:
        # 从当前编辑参数组读取
        edit_profile = cfg.get_edit_profile()
        profile = cfg.get_profile(edit_profile)
        val = int(profile.get(key, 0)) if profile else 0
    else:
        # 从全局配置读取
        val = int(cfg.get_config(key, 0))

    dpg.add_drag_int(
        label=label,
        default_value=val,
        min_value=min_v,
        max_value=max_v,
        callback=update_config_callback,
        user_data=key,
        width=280,
        tag=tag
    )


def add_bool_tagged(key, label, tag=None, callback=None):
    _register_tagged(key, tag)

    if key in PROFILE_KEYS:
        edit_profile = cfg.get_edit_profile()
        profile = cfg.get_profile(edit_profile)
        val = bool(profile.get(key, False)) if profile else False
    else:
        val = bool(cfg.get_config(key, False))

    if callback:
        def wrapped_callback(sender, app_data, user_data):
            update_config_callback(sender, app_data, user_data)
            callback(sender, app_data, user_data)

        dpg.add_checkbox(
            label=label,
            default_value=val,
            callback=wrapped_callback,
            user_data=key,
            tag=tag
        )
    else:
        dpg.add_checkbox(
            label=label,
            default_value=val,
            callback=update_config_callback,
            user_data=key,
            tag=tag
        )



def add_input_text_tagged(key, label, tag=None):
    _register_tagged(key, tag)

    if key in PROFILE_KEYS:
        edit_profile = cfg.get_edit_profile()
        profile = cfg.get_profile(edit_profile)
        val = str(profile.get(key, "")) if profile else ""
    else:
        val = str(cfg.get_config(key, ""))

    dpg.add_input_text(
        label=label,
        default_value=val,
        callback=update_config_callback,
        user_data=key,
        width=280,
        tag=tag
    )



def add_float_input_tagged(key, label, tag=None, format="%.3f", callback=None):
    _register_tagged(key, tag)

    if key in PROFILE_KEYS:
        edit_profile = cfg.get_edit_profile()
        profile = cfg.get_profile(edit_profile)
        val = float(profile.get(key, 0.0)) if profile else 0.0
    else:
        val = float(cfg.get_config(key, 0.0))

    if callback:
        def wrapped_callback(sender, app_data, user_data):
            update_config_callback(sender, app_data, user_data)
            callback(sender, app_data, user_data)

        dpg.add_input_float(
            label=label,
            default_value=val,
            tag=tag,
            step=0,
            format=format,
            width=280,
            callback=wrapped_callback,
            user_data=key
        )
    else:
        dpg.add_input_float(
            label=label,
            default_value=val,
            tag=tag,
            step=0,
            format=format,
            width=280,
            callback=update_config_callback,
            user_data=key
        )

def add_int_input_tagged(key, label, tag=None):
    _register_tagged(key, tag)

    if key in PROFILE_KEYS:
        edit_profile = cfg.get_edit_profile()
        profile = cfg.get_profile(edit_profile)
        val = int(profile.get(key, 0)) if profile else 0
    else:
        val = int(cfg.get_config(key, 0))

    dpg.add_input_int(
        label=label,
        default_value=val,
        tag=tag,
        step=0,
        width=280,
        callback=update_config_callback,
        user_data=key
    )


def add_combo_tagged(key, label, items, tag=None):
    _register_tagged(key, tag)

    if key in PROFILE_KEYS:
        edit_profile = cfg.get_edit_profile()
        profile = cfg.get_profile(edit_profile)
        val = str(profile.get(key, items[0])) if profile else items[0]
    else:
        val = str(cfg.get_config(key, items[0] if items else ""))

    if val not in items:
        items.append(val)

    dpg.add_combo(
        label=label,
        items=items,
        default_value=val,
        callback=update_config_callback,
        user_data=key,
        width=280,
        tag=tag
    )