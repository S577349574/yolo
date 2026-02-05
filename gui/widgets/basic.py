import dearpygui.dearpygui as dpg

import config_manager as cfg
from widgets.callbacks import update_config_callback


def add_float(key, label, min_v=0.0, max_v=1.0, speed=0.01):
    val = float(cfg.get_config(key, 0.0))
    dpg.add_drag_float(
        label=label,
        default_value=val,
        min_value=min_v,
        max_value=max_v,
        speed=speed,
        callback=update_config_callback,
        user_data=key,
        width=280
    )


def add_int(key, label, min_v=0, max_v=100):
    val = int(cfg.get_config(key, 0))
    dpg.add_drag_int(
        label=label,
        default_value=val,
        min_value=min_v,
        max_value=max_v,
        callback=update_config_callback,
        user_data=key,
        width=280
    )


def add_bool(key, label):
    val = bool(cfg.get_config(key, False))
    dpg.add_checkbox(
        label=label,
        default_value=val,
        callback=update_config_callback,
        user_data=key
    )


def add_input_text(key, label):
    val = str(cfg.get_config(key, ""))
    dpg.add_input_text(
        label=label,
        default_value=val,
        callback=update_config_callback,
        user_data=key,
        width=280
    )


def add_combo(key, label, items):
    val = str(cfg.get_config(key, items[0]))
    if val not in items:
        items.append(val)
    dpg.add_combo(
        label=label,
        items=items,
        default_value=val,
        callback=update_config_callback,
        user_data=key,
        width=280
    )
