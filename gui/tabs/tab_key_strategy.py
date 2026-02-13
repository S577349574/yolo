# tab_key_strategy.py

import dearpygui.dearpygui as dpg
from config import config_manager as cfg
from gui.theme.apple_theme import create_table_header_theme
from gui.theme.colors import UIColors
from gui.widgets.callbacks import update_config_callback

SUPPORTED_KEYS = ["left", "right", "mouse4", "mouse5"]

# ==========================
# 中文映射
# ==========================

MODE_MAP = {
    "按住生效": "hold",
    "按下切换": "toggle"
}
MODE_MAP_REVERSE = {v: k for k, v in MODE_MAP.items()}

FALLBACK_POLICY_MAP = {
    "恢复之前的参数组": "previous",
    "恢复指定的参数组": "fallback"
}
FALLBACK_POLICY_REVERSE = {v: k for k, v in FALLBACK_POLICY_MAP.items()}


# ==========================
# 工具函数 - 嵌套配置读写
# ==========================

def _get_binding_field(key, field, default=None):
    """读取 KEY_PROFILE_BINDINGS[key][field]"""
    bindings = cfg.get_config("KEY_PROFILE_BINDINGS", {}) or {}
    entry = bindings.get(key, {})
    return entry.get(field, default)


def _set_binding_field(key, field, value):
    """写入 KEY_PROFILE_BINDINGS[key][field]"""
    bindings = cfg.get_config("KEY_PROFILE_BINDINGS", {}) or {}

    # 清理脏 key
    bindings.pop(None, None)
    bindings.pop("null", None)

    if key not in bindings:
        bindings[key] = {}

    bindings[key][field] = value
    cfg.set_config("KEY_PROFILE_BINDINGS", bindings)


def _mark_dirty_status(text: str):
    """统一的未保存状态提示"""
    if dpg.does_item_exist("status_text"):
        dpg.configure_item(
            "status_text",
            default_value=text,
            color=UIColors.WARNING_ORANGE
        )


def _ensure_valid_fallback_profile():
    """
    确保 KEY_PROFILE_FALLBACK 是有效 profile。
    - 如果当前值不在 profiles 里，则改为 default 或第一个 profile 或空字符串。
    """
    profiles = cfg.list_profiles() or []
    current = cfg.get_config("KEY_PROFILE_FALLBACK", "default")

    if current in profiles:
        return current

    # 纠正为 default / 第一个 / 空
    fixed = "default" if "default" in profiles else (profiles[0] if profiles else "")
    cfg.set_config("KEY_PROFILE_FALLBACK", fixed)
    return fixed


# ==========================
# 回调函数
# ==========================

def update_binding_callback(sender, app_data, user_data):
    """
    标准化的配置更新回调
    user_data = (key, field) 元组
    """
    if not user_data or len(user_data) != 2:
        print(f"[ERROR] update_binding_callback: invalid user_data={user_data}")
        return

    key, field = user_data
    _set_binding_field(key, field, app_data)

    _mark_dirty_status(f"[未保存] 已修改按键策略: {key}.{field}")


def update_chinese_mapping_callback(sender, app_data, user_data):
    """
    中文映射转换回调
    user_data = (key, field, mapping_dict)
    """
    if not user_data or len(user_data) != 3:
        print(f"[ERROR] update_chinese_mapping_callback: invalid user_data={user_data}")
        return

    key, field, mapping = user_data

    # 将中文选项转换为英文值
    english_value = mapping.get(app_data, app_data)
    _set_binding_field(key, field, english_value)

    _mark_dirty_status(f"[未保存] 已修改按键策略: {key}.{field}")


def update_priority_from_table_columns():
    """从表格列顺序更新优先级"""
    if not dpg.does_item_exist("key_bindings_table"):
        return

    # 获取所有列
    columns = dpg.get_item_children("key_bindings_table", slot=0)  # slot=0 是列容器
    if not columns:
        return

    # 提取按键顺序（跳过第一列"配置项"）
    priority_order = []
    for col_id in columns[1:]:  # 跳过第一列
        user_data = dpg.get_item_user_data(col_id)
        if user_data and isinstance(user_data, str):
            priority_order.append(user_data)

    if priority_order:
        cfg.set_config("KEY_PROFILE_PRIORITY", priority_order)
        _mark_dirty_status("[未保存] 已修改按键优先级(拖动列顺序)")


def refresh_profile_combo_callback(sender, app_data, user_data):
    """
    下拉框打开时刷新 profiles 列表
    user_data = combo_item_id
    """
    combo_id = user_data
    if combo_id and dpg.does_item_exist(combo_id):
        profiles = [""] + (cfg.list_profiles() or [])
        current_value = dpg.get_value(combo_id)

        dpg.configure_item(combo_id, items=profiles)

        if current_value in profiles:
            dpg.set_value(combo_id, current_value)
        else:
            dpg.set_value(combo_id, "")


def refresh_fallback_combo_callback(sender, app_data, user_data):
    """
    刷新 Fallback 参数组下拉列表
    user_data = combo_item_id
    """
    combo_id = user_data
    if combo_id and dpg.does_item_exist(combo_id):
        profiles = cfg.list_profiles() or []
        current_value = dpg.get_value(combo_id)

        dpg.configure_item(combo_id, items=profiles)

        # 同步校验：如果当前值不存在，纠正为 default/第一个/空
        if current_value in profiles:
            dpg.set_value(combo_id, current_value)
        else:
            fixed = "default" if "default" in profiles else (profiles[0] if profiles else "")
            dpg.set_value(combo_id, fixed)
            cfg.set_config("KEY_PROFILE_FALLBACK", fixed)


def on_hold_policy_changed(sender, app_data):
    """
    松开后执行操作 改变时：
    1) 写入 HOLD_FALLBACK_POLICY
    2) 动态显示/隐藏 fallback combo
    3) 若切到 fallback，则保证 KEY_PROFILE_FALLBACK 合法，并同步 UI 值
    """
    policy = FALLBACK_POLICY_MAP.get(app_data, "previous")
    cfg.set_config("HOLD_FALLBACK_POLICY", policy)

    # 动态显示/隐藏 “指定的参数组”
    if dpg.does_item_exist("fallback_profile_combo"):
        dpg.configure_item("fallback_profile_combo", show=(policy == "fallback"))

        if policy == "fallback":
            # 切换到 fallback 时，确保配置合法并同步 UI
            fixed = _ensure_valid_fallback_profile()
            profiles = cfg.list_profiles() or []
            dpg.configure_item("fallback_profile_combo", items=profiles)
            dpg.set_value("fallback_profile_combo", fixed)

    _mark_dirty_status("[未保存] 已修改松开恢复策略")


# ==========================
# UI 构建
# ==========================

def build_key_strategy_tab():
    with dpg.tab(label="按键策略"):
        dpg.add_text("按键参数组触发系统(全局设置)", color=UIColors.APPLE_BLUE)

        # 全局开关
        dpg.add_checkbox(
            label="启用按键参数组绑定",
            default_value=cfg.get_config("ENABLE_KEY_PROFILE_BINDING", True),
            callback=update_config_callback,
            user_data="ENABLE_KEY_PROFILE_BINDING"
        )

        dpg.add_separator()

        # ======================
        # 按键绑定表格
        # ======================
        dpg.add_text("按键绑定设置", color=UIColors.SECTION_HEADER)
        dpg.add_text(
            "提示: 拖动按键列(LEFT/RIGHT/MOUSE4/MOUSE5)可调整优先级,从左到右优先级递减",
            color=UIColors.TEXT_GRAY
        )

        profiles = [""] + (cfg.list_profiles() or [])

        current_priority = cfg.get_config("KEY_PROFILE_PRIORITY", SUPPORTED_KEYS.copy())

        ordered_keys = []
        for key in current_priority:
            if key in SUPPORTED_KEYS:
                ordered_keys.append(key)
        for key in SUPPORTED_KEYS:
            if key not in ordered_keys:
                ordered_keys.append(key)

        table_theme = create_table_header_theme()
        with dpg.table(
            tag="key_bindings_table",
            header_row=True,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            row_background=True,
            reorderable=True,
            callback=update_priority_from_table_columns,
            policy=dpg.mvTable_SizingFixedFit
        ):
            dpg.bind_item_theme("key_bindings_table", table_theme)

            dpg.add_table_column(
                label="配置项",
                width_fixed=True,
                init_width_or_weight=100,
                no_reorder=True
            )

            for key in ordered_keys:
                dpg.add_table_column(
                    label=key.upper(),
                    width_fixed=True,
                    init_width_or_weight=150,
                    user_data=key
                )

            dpg.add_table_column(
                label="",
                width_stretch=False,
                no_reorder=True,
                no_sort=True,
                no_resize=True
            )

            # 第1行: 绑定参数组
            with dpg.table_row():
                dpg.add_text("绑定参数组")
                for key in ordered_keys:
                    current_profile = _get_binding_field(key, "profile", "")
                    combo_tag = f"key_profile_combo_{key}"
                    combo_id = dpg.add_combo(
                        tag=combo_tag,
                        items=profiles,
                        default_value=current_profile if current_profile else "",
                        width=-1,
                        callback=update_binding_callback,
                        user_data=(key, "profile")
                    )

                    with dpg.item_handler_registry() as handler:
                        dpg.add_item_focus_handler(
                            callback=refresh_profile_combo_callback,
                            user_data=combo_tag
                        )
                    dpg.bind_item_handler_registry(combo_id, handler)

            # 第2行: 按键模式
            with dpg.table_row():
                dpg.add_text("按键模式")
                for key in ordered_keys:
                    current_mode = _get_binding_field(key, "mode", "hold")
                    dpg.add_combo(
                        items=list(MODE_MAP.keys()),
                        default_value=MODE_MAP_REVERSE.get(current_mode, "按住生效"),
                        width=-1,
                        callback=update_chinese_mapping_callback,
                        user_data=(key, "mode", MODE_MAP)
                    )

            # 第3行: 触发逻辑
            with dpg.table_row():
                dpg.add_text("触发逻辑")
                for key in ordered_keys:
                    current_trigger = _get_binding_field(key, "trigger", True)
                    dpg.add_checkbox(
                        default_value=current_trigger,
                        callback=update_binding_callback,
                        user_data=(key, "trigger")
                    )

        dpg.add_separator()

        # ======================
        # Hold 策略
        # ======================

        dpg.add_text("松开按键后的恢复策略", color=UIColors.SECTION_HEADER)

        # Hold 结束策略
        current_policy = cfg.get_config("HOLD_FALLBACK_POLICY", "previous")
        dpg.add_combo(
            label="松开后执行操作",
            items=list(FALLBACK_POLICY_MAP.keys()),
            default_value=FALLBACK_POLICY_REVERSE.get(current_policy, "恢复之前的参数组"),
            width=280,
            callback=on_hold_policy_changed
        )

        # fallback 参数组
        fallback_combo_tag = "fallback_profile_combo"

        # 进入 UI 时就先保证 KEY_PROFILE_FALLBACK 合法（避免默认值不在 profiles）
        fixed_fallback = _ensure_valid_fallback_profile()
        fallback_combo_id = dpg.add_combo(
            tag=fallback_combo_tag,
            label="指定的参数组",
            items=(cfg.list_profiles() or []),
            default_value=fixed_fallback,
            width=280,
            callback=update_config_callback,
            user_data="KEY_PROFILE_FALLBACK",
            show=(current_policy == "fallback")
        )

        with dpg.item_handler_registry() as fallback_handler:
            dpg.add_item_focus_handler(
                callback=refresh_fallback_combo_callback,
                user_data=fallback_combo_tag
            )
        dpg.bind_item_handler_registry(fallback_combo_id, fallback_handler)

        dpg.add_separator()

        dpg.add_text(
            "  这个界面最后设置，先把参数组调好\n"
            "  \n"
            "• 【绑定参数组】留空表示该按键不切换参数组\n"
            "• 【按住生效】按住期间临时切换参数组,松开后恢复\n"
            "• 【按下切换】点击一下啊切换到对用的参数组\n"
            "• 【触发逻辑】如果触发逻辑勾选，按住的时候触发吸附压枪等功能\n"
            "• 【恢复策略】如果你使用的按住模式，并且勾选了触发逻辑，那么直接无视这个选项\n",
            color=UIColors.TEXT_GRAY
        )
