import dearpygui.dearpygui as dpg

import config_manager as cfg
from gui.widgets.callbacks import update_config_callback

_TAGGED_KEY_TO_TAG = {}
_TAGGED_TAG_TO_KEY = {}


def _register_tagged(key: str, tag: str | None):
    """记录 key<->tag 的映射，供切换参数组时批量刷新 UI"""
    if not tag:
        return
    _TAGGED_KEY_TO_TAG[key] = tag
    _TAGGED_TAG_TO_KEY[tag] = key


def refresh_all_tagged_controls():
    """把当前全局配置(cfg.get_config)刷新到所有通过 tagged.py 创建的控件"""
    for key, tag in _TAGGED_KEY_TO_TAG.items():
        if not dpg.does_item_exist(tag):
            continue
        try:
            dpg.set_value(tag, cfg.get_config(key))
        except Exception as e:
            print(f"[GUI] 刷新控件失败 key={key} tag={tag}: {e}")


def add_float_tagged(key, label, min_v=0.0, max_v=1.0, tag=None, speed=0.01):
    _register_tagged(key, tag)
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


def add_int_tagged(key, label, min_v=0, max_v=100, tag=None):
    _register_tagged(key, tag)
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
    """
    ✅ 新增 callback 参数支持

    Args:
        key: 配置键名
        label: 显示标签
        tag: UI 控件标签
        callback: 自定义回调函数 (可选)
                 如果提供，会在更新配置后调用
                 签名: callback(sender, app_data, user_data)
    """
    _register_tagged(key, tag)
    val = bool(cfg.get_config(key, False))

    # ✅ 如果有自定义 callback，包装它
    if callback:
        def wrapped_callback(sender, app_data, user_data):
            # 先更新配置
            update_config_callback(sender, app_data, user_data)
            # 再调用自定义逻辑
            callback(sender, app_data, user_data)

        dpg.add_checkbox(
            label=label,
            default_value=val,
            callback=wrapped_callback,
            user_data=key,
            tag=tag
        )
    else:
        # 没有自定义 callback，使用默认的
        dpg.add_checkbox(
            label=label,
            default_value=val,
            callback=update_config_callback,
            user_data=key,
            tag=tag
        )


def add_input_text_tagged(key, label, tag=None):
    _register_tagged(key, tag)
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
    """
    ✅ 新增 callback 参数支持

    Args:
        key: 配置键名
        label: 显示标签
        tag: UI 控件标签
        format: 数字格式
        callback: 自定义回调函数 (可选)
                 如果提供，会在更新配置后调用
                 签名: callback(sender, app_data, user_data)
    """
    _register_tagged(key, tag)
    val = float(cfg.get_config(key, 0.0))

    # ✅ 如果有自定义 callback，包装它
    if callback:
        def wrapped_callback(sender, app_data, user_data):
            # 先更新配置
            update_config_callback(sender, app_data, user_data)
            # 再调用自定义逻辑
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
        # 没有自定义 callback，使用默认的
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
    val = str(cfg.get_config(key, items[0]))
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
