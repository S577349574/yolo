import dearpygui.dearpygui as dpg

import config_manager as cfg
from gui.theme.colors import UIColors


def update_search_bounds(key, value):
    """更新搜索区域配置并实时显示（保存到参数组）"""
    bounds = cfg.get_config("CROSSHAIR_SEARCH_BOUNDS", {
        "x_left": -30,
        "x_right": 30,
        "y_up": -150,
        "y_down": 20
    })

    bounds[key] = value
    bounds[key] = max(-500, min(500, bounds[key]))

    # ✅ 1. 更新全局配置
    cfg.set_config("CROSSHAIR_SEARCH_BOUNDS", bounds)

    # ✅ 2. 同步到当前参数组（关键修复）
    active_profile = cfg.get_active_profile()
    cfg.sync_profile_from_global(active_profile)

    # ✅ 3. 更新状态提示
    dpg.configure_item(
        "status_text",
        default_value=f"[未保存] 已修改搜索区域: {key}",
        color=UIColors.WARNING_ORANGE
    )

    # ✅ 4. 更新显示文字
    if dpg.does_item_exist("crosshair_search_area_display"):
        width = bounds["x_right"] - bounds["x_left"]
        height = abs(bounds["y_up"]) + bounds["y_down"]
        dpg.configure_item(
            "crosshair_search_area_display",
            default_value=f"当前搜索区域: {width}×{height} 像素"
        )


def _handle_preview_drag(sender, app_data):
    """处理预览框内的鼠标拖拽/点击事件"""
    if not dpg.does_item_exist("aim_preview_drawlist"):
        return

    local_mouse_pos = dpg.get_mouse_pos(local=True)
    rel_x = local_mouse_pos[0]
    rel_y = local_mouse_pos[1]

    canvas_w, canvas_h = 100, 160
    rect_w, rect_h = 60, 130
    rect_x_start = (canvas_w - rect_w) // 2
    rect_y_start = 10

    new_x_ratio = max(0.0, min(1.0, (rel_x - rect_x_start) / rect_w))
    new_y_ratio = max(0.0, min(1.0, (rel_y - rect_y_start) / rect_h))

    # ✅ 1. 更新全局配置
    cfg.set_config("AIM_X_OFFSET", round(new_x_ratio, 3))
    cfg.set_config("AIM_Y_RATIO", round(new_y_ratio, 3))

    # ✅ 2. 同步到当前参数组（关键修复）
    active_profile = cfg.get_active_profile()
    cfg.sync_profile_from_global(active_profile)

    # ✅ 3. 更新 UI 控件
    if dpg.does_item_exist("input_aim_x"):
        dpg.set_value("input_aim_x", round(new_x_ratio, 3))
    if dpg.does_item_exist("input_aim_y"):
        dpg.set_value("input_aim_y", round(new_y_ratio, 3))

    # ✅ 4. 更新预览图
    update_aim_offset_preview()
    # ✅ 5. 提示用户（可选）
    if dpg.does_item_exist("status_text"):
        dpg.configure_item(
            "status_text",
            default_value=f"[未保存] 已修改瞄准偏移: X={new_x_ratio:.3f}, Y={new_y_ratio:.3f}",
            color=UIColors.WARNING_ORANGE
        )


def update_aim_offset_preview():
    """实时更新 PID 瞄准偏移预览图"""
    if not dpg.does_item_exist("aim_preview_node"):
        return

    dpg.delete_item("aim_preview_node", children_only=True)

    canvas_w, canvas_h = 100, 160
    rect_w, rect_h = 60, 130
    rect_x = (canvas_w - rect_w) // 2
    rect_y = 10

    offset_x = cfg.get_config("AIM_X_OFFSET", 0.5)
    offset_y = cfg.get_config("AIM_Y_RATIO", 0.5)

    dpg.draw_rectangle(
        [rect_x + 2, rect_y + 2],
        [rect_x + rect_w + 2, rect_y + rect_h + 2],
        color=(0, 0, 0, 20),
        fill=(0, 0, 0, 20),
        rounding=5,
        parent="aim_preview_node"
    )

    dpg.draw_rectangle(
        [rect_x, rect_y],
        [rect_x + rect_w, rect_y + rect_h],
        color=(180, 180, 180, 255),
        fill=(255, 255, 255, 255),
        thickness=1,
        rounding=5,
        parent="aim_preview_node"
    )

    center_y = rect_y + rect_h // 2
    center_x = rect_x + rect_w // 2
    dpg.draw_line(
        [rect_x, center_y],
        [rect_x + rect_w, center_y],
        color=(230, 230, 230, 255),
        parent="aim_preview_node"
    )
    dpg.draw_line(
        [center_x, rect_y],
        [center_x, rect_y + rect_h],
        color=(230, 230, 230, 255),
        parent="aim_preview_node"
    )

    dot_x = rect_x + (rect_w * offset_x)
    dot_y = rect_y + (rect_h * offset_y)

    dpg.draw_circle(
        [dot_x, dot_y],
        8,
        color=(255, 59, 48, 50),
        fill=(255, 59, 48, 30),
        parent="aim_preview_node"
    )
    dpg.draw_circle(
        [dot_x, dot_y],
        4,
        color=(255, 59, 48, 255),
        fill=(255, 59, 48, 255),
        parent="aim_preview_node"
    )

    dpg.draw_text(
        [10, 145],
        f"Target: ({offset_x:.2f}, {offset_y:.2f})",
        color=UIColors.TEXT_BLACK,
        size=12,
        parent="aim_preview_node"
    )
