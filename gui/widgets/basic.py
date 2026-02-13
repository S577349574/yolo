import dearpygui.dearpygui as dpg

from config import config_manager as cfg
from gui.widgets.callbacks import update_config_callback
from gui.widgets.tagged import _register_tagged


def _auto_tag(key: str) -> str:
    return f"cfg_{key.lower()}"


def add_float(key, label, min_v=0.0, max_v=1.0, speed=0.01):
    tag = _auto_tag(key)
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


def add_int(key, label, min_v=0, max_v=100):
    tag = _auto_tag(key)
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


def add_bool(key, label):
    tag = _auto_tag(key)
    _register_tagged(key, tag)

    val = bool(cfg.get_config(key, False))
    dpg.add_checkbox(
        label=label,
        default_value=val,
        callback=update_config_callback,
        user_data=key,
        tag=tag
    )


def add_input_text(key, label):
    tag = _auto_tag(key)
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


def add_combo(key, label, items):
    tag = _auto_tag(key)
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
def _get_nested(root_key: str, path: list, default=None):
    root = cfg.get_config(root_key, {}) or {}
    cur = root
    for p in path[:-1]:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p, {})
    if not isinstance(cur, dict):
        return default
    return cur.get(path[-1], default)


def _set_nested(root_key: str, path: list, value):
    root = cfg.get_config(root_key, {}) or {}

    # 清理脏 key
    root.pop(None, None)
    root.pop("null", None)

    cur = root
    for p in path[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]

    cur[path[-1]] = value
    cfg.set_config(root_key, root)
