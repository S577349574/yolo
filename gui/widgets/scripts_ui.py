import glob
import os

import dearpygui.dearpygui as dpg

from config import config_manager as cfg
import utils
from gui.theme.colors import UIColors


def update_script_state_callback(sender, app_data, user_data):
    script_name = user_data
    is_enabled = app_data

    current_enabled = cfg.get_config("ENABLED_SCRIPTS", [])
    if isinstance(current_enabled, str):
        current_enabled = [s.strip() for s in current_enabled.split(",") if s.strip()]

    if is_enabled:
        if script_name not in current_enabled:
            current_enabled.append(script_name)
    else:
        if script_name in current_enabled:
            current_enabled.remove(script_name)

    cfg.set_config("ENABLED_SCRIPTS", current_enabled)

    refresh_scripts_ui()


def refresh_scripts_ui():
    SCRIPTS_DIR = utils.get_scripts_dir()
    print(f"[UI Debug] 正在扫描脚本目录: {SCRIPTS_DIR}")

    # ✅ 关键防御：parent 不存在直接返回
    if not dpg.does_item_exist("script_list_container"):
        print("[UI Debug] script_list_container 不存在，跳过刷新")
        return

    # 清空旧内容
    dpg.delete_item("script_list_container", children_only=True)

    if not os.path.exists(SCRIPTS_DIR):
        os.makedirs(SCRIPTS_DIR)

    lua_files = glob.glob(os.path.join(SCRIPTS_DIR, "*.lua"))
    script_names = [os.path.splitext(os.path.basename(f))[0] for f in lua_files]

    enabled_config = cfg.get_config("ENABLED_SCRIPTS", [])
    if isinstance(enabled_config, str):
        enabled_scripts = [s.strip() for s in enabled_config.split(",") if s.strip()]
    else:
        enabled_scripts = enabled_config

    if not script_names:
        dpg.add_text(
            "未找到脚本文件 (请在 scripts/ 文件夹放入 .lua)",
            parent="script_list_container",
            color=UIColors.TEXT_GRAY
        )
        return

    for name in script_names:
        is_active = name in enabled_scripts

        # ✅ 推荐：不用 with，调试期更安全
        row = dpg.add_group(horizontal=True, parent="script_list_container")

        dpg.add_checkbox(
            label=f"{name}.lua",
            default_value=is_active,
            callback=update_script_state_callback,
            user_data=name,
            parent=row
        )

        dpg.add_text(
            "(已启用)" if is_active else "(未启用)",
            color=UIColors.SUCCESS_GREEN if is_active else UIColors.TEXT_GRAY,
            parent=row
        )
