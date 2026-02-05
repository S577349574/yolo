import dearpygui.dearpygui as dpg

import config_manager as cfg
from widgets.callbacks import update_config_callback


def add_float_tagged(key, label, min_v=0.0, max_v=1.0, tag=None, speed=0.01):
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


def add_bool_tagged(key, label, tag=None):
    val = bool(cfg.get_config(key, False))
    dpg.add_checkbox(
        label=label,
        default_value=val,
        callback=update_config_callback,
        user_data=key,
        tag=tag
    )


def add_input_text_tagged(key, label, tag=None):
    val = str(cfg.get_config(key, ""))
    dpg.add_input_text(
        label=label,
        default_value=val,
        callback=update_config_callback,
        user_data=key,
        width=280,
        tag=tag
    )


def add_float_input_tagged(key, label, tag=None, format="%.3f"):
    """专门用于数字输入，无加减号，宽度一致"""
    val = float(cfg.get_config(key, 0.0))
    dpg.add_input_float(
        label=label,
        default_value=val,
        tag=tag,
        step=0,
        format=format,
        width=280,
        callback=lambda s, a: cfg.set_config(key, a)
    )


def add_int_input_tagged(key, label, tag=None):
    """专门用于整数输入，无加减号，宽度一致"""
    val = int(cfg.get_config(key, 0))
    dpg.add_input_int(
        label=label,
        default_value=val,
        tag=tag,
        step=0,
        width=280,
        callback=lambda s, a: cfg.set_config(key, a)
    )


def add_combo_tagged(key, label, items, tag=None):
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
