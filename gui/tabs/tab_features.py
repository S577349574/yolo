import dearpygui.dearpygui as dpg

from gui.theme.colors import UIColors

from gui.widgets.tagged import add_combo_tagged
from gui.widgets.helpers import update_dependent_controls
from gui.widgets.callbacks import update_class_ids_callback
from gui.widgets.crosshair_preview import generate_crosshair_preview_callback
from gui.widgets.preview import update_search_bounds
from gui.widgets.tagged import (
    add_input_text_tagged, add_bool_tagged, add_int_tagged,
    add_float_input_tagged, add_int_input_tagged, add_float_tagged,refresh_all_tagged_controls
)

import config_manager as cfg

from gui.widgets.basic import add_float

from gui.widgets.basic import add_int

from gui.widgets.preview import update_aim_offset_preview


# ---------------------------- 参数组管理：UI 刷新 ----------------------------

def _safe_set(tag: str, value):
    if dpg.does_item_exist(tag):
        dpg.set_value(tag, value)


def refresh_ui_from_config():
    """把当前全局 config 的值刷新到 UI 控件上（切换参数组后调用）"""

    # ===== 准星检测 =====
    _safe_set("crosshair_detector_type", cfg.get_config("CROSSHAIR_DETECTOR_TYPE"))
    _safe_set("crosshair_valorant_config", cfg.get_config("CROSSHAIR_VALORANT_CONFIG"))
    _safe_set("crosshair_template_path", cfg.get_config("CROSSHAIR_TEMPLATE_PATH"))
    _safe_set("crosshair_use_fallback", cfg.get_config("CROSSHAIR_USE_FALLBACK_CENTER"))
    _safe_set("crosshair_debug_mode", cfg.get_config("CROSSHAIR_DEBUG_MODE"))
    _safe_set("crosshair_stats_interval", cfg.get_config("CROSSHAIR_STATS_INTERVAL"))

    bounds = cfg.get_config("CROSSHAIR_SEARCH_BOUNDS", {})
    _safe_set("crosshair_search_x_left", bounds.get("x_left", -30))
    _safe_set("crosshair_search_x_right", bounds.get("x_right", 30))
    _safe_set("crosshair_search_y_up", bounds.get("y_up", -150))
    _safe_set("crosshair_search_y_down", bounds.get("y_down", 20))

    # 搜索区域显示文字
    if dpg.does_item_exist("crosshair_search_area_display"):
        current_width = bounds.get("x_right", 30) - bounds.get("x_left", -30)
        current_height = abs(bounds.get("y_up", -150)) + bounds.get("y_down", 20)
        dpg.configure_item(
            "crosshair_search_area_display",
            default_value=f"当前搜索区域: {current_width}×{current_height} 像素"
        )

    _safe_set("crosshair_smooth_factor", cfg.get_config("CROSSHAIR_SMOOTH_FACTOR"))
    _safe_set("crosshair_max_lost_frames", cfg.get_config("CROSSHAIR_MAX_LOST_FRAMES"))

    # ===== PID 瞄准 =====
    _safe_set("input_aim_y", cfg.get_config("AIM_Y_RATIO"))
    _safe_set("input_aim_x", cfg.get_config("AIM_X_OFFSET"))

def update_combo_box():
    """更新参数组 ComboBox 的 items 与当前选中值"""
    names = cfg.list_profiles()
    active = cfg.get_active_profile()

    if dpg.does_item_exist("profile_combo_box"):
        dpg.configure_item("profile_combo_box", items=names)
        # 确保当前值是 items 里的值
        if active in names:
            dpg.set_value("profile_combo_box", active)
        elif names:
            dpg.set_value("profile_combo_box", names[0])


# ---------------------------- 参数组管理：回调 ----------------------------

def on_profile_change(profile_name):
    try:
        if not cfg.set_active_profile(profile_name):
            print(f"切换失败: {profile_name}")
            return

        # 1) 刷新所有 tagged 控件（值会跟随 profile 切换）
        refresh_all_tagged_controls()

        refresh_target_class_ids_checkboxes()  # ✅ 新增
        # 2) 刷新未标记的控件（例如手写的 input_int 搜索区域）
        refresh_non_tagged_controls()

        # 3) 重新应用各“主开关”的依赖控件启用/禁用状态（关键：切 profile 不会自动触发 callback）
        # --- 准星检测总开关 ---
        update_dependent_controls(
            "ENABLE_CROSSHAIR_DETECTION",
            [
                "crosshair_detector_type",
                "crosshair_valorant_config",
                "crosshair_preview_btn",
                "crosshair_template_path",
                "crosshair_use_fallback",
                "crosshair_debug_mode",
                "crosshair_stats_interval",
                "crosshair_search_x_left",
                "crosshair_search_x_right",
                "crosshair_search_y_up",
                "crosshair_search_y_down",
                "crosshair_smooth_factor",
                "crosshair_max_lost_frames"
            ],
            cfg.get_config("ENABLE_CROSSHAIR_DETECTION", True)
        )

        # --- 视觉识别：头部优先 ---
        update_dependent_controls(
            "ENABLE_HEAD_PRIORITY",
            ["body_class_id","head_class_id", "head_priority_range", "ignore_small_head", "small_target_threshold"],
            cfg.get_config("ENABLE_HEAD_PRIORITY", True)
        )

        # --- 视觉识别：忽略小目标头部 ---
        update_dependent_controls(
            "IGNORE_SMALL_TARGET_HEAD",
            ["small_target_threshold"],
            cfg.get_config("IGNORE_SMALL_TARGET_HEAD", True)
        )

        # --- 目标追踪：卡尔曼滤波 ---
        update_dependent_controls(
            "USE_KALMAN_FILTER",
            ["kalman_process", "kalman_measure", "kalman_predict"],
            cfg.get_config("USE_KALMAN_FILTER", True)
        )

        # --- 目标追踪：移动预判 ---
        update_dependent_controls(
            "ENABLE_LEAD_TARGET",
            ["lead_frames"],
            cfg.get_config("ENABLE_LEAD_TARGET", False)
        )

        # --- 压枪系统总开关 ---
        update_dependent_controls(
            "ENABLE_MANUAL_RECOIL",
            [
                "recoil_ctrl", "recoil_mode", "recoil_req_target", "recoil_req_lock",
                "recoil_timeout", "recoil_lock_frames", "recoil_pattern", "recoil_v_speed",
                "recoil_h_speed", "recoil_inc_y", "recoil_h_var", "recoil_max_move",
                "recoil_max_x", "recoil_max_y"
            ],
            cfg.get_config("ENABLE_MANUAL_RECOIL", True)
        )

        # --- 自动开火总开关 ---
        update_dependent_controls(
            "ENABLE_AUTO_FIRE",
            ["autofire_debug", "autofire_acc", "autofire_dist", "autofire_lock"],
            cfg.get_config("ENABLE_AUTO_FIRE", False)
        )

        print(f"已切换到参数组: {profile_name}")

        # 其他联动预览刷新
        update_aim_offset_preview()

    except Exception as e:
        print(f"切换失败: {profile_name}, error={e}")



def refresh_non_tagged_controls():
    # 搜索区域（你这里是手写 input_int，不是 tagged.py 创建的）
    bounds = cfg.get_config("CROSSHAIR_SEARCH_BOUNDS", {})
    for k, tag in [
        ("x_left", "crosshair_search_x_left"),
        ("x_right", "crosshair_search_x_right"),
        ("y_up", "crosshair_search_y_up"),
        ("y_down", "crosshair_search_y_down"),
    ]:
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, bounds.get(k))

    # 搜索区域显示文字
    if dpg.does_item_exist("crosshair_search_area_display"):
        current_width = bounds.get("x_right", 30) - bounds.get("x_left", -30)
        current_height = abs(bounds.get("y_up", -150)) + bounds.get("y_down", 20)
        dpg.configure_item(
            "crosshair_search_area_display",
            default_value=f"当前搜索区域: {current_width}×{current_height} 像素"
        )

def create_new_profile():
    name = (dpg.get_value("new_profile_name") or "").strip()
    if not name:
        print("请输入有效的参数组名称")
        return

    try:
        cfg.create_profile(name)
        update_combo_box()

        # ✅ 统一走完整切换刷新
        on_profile_change(name)

        print(f"成功创建新参数组: {name}")
    except Exception as e:
        print(f"创建参数组失败: {name}, error={e}")


def delete_profile_ui():
    """删除当前参数组（支持删除激活组）"""
    active = cfg.get_active_profile()

    # ✅ 1. 检查是否是 default 组
    if active == "default":
        print("❌ 不能删除 default 参数组")
        if dpg.does_item_exist("status_text"):
            dpg.configure_item(
                "status_text",
                default_value="[错误] 不能删除 default 参数组",
                color=(255, 59, 48, 255)  # 红色
            )
        return

    try:
        # ✅ 2. 先切换到 default（或其他可用组）
        names = cfg.list_profiles()
        fallback = "default" if "default" in names else None

        if not fallback:
            # 如果连 default 都不存在，找第一个不是当前组的
            fallback = next((n for n in names if n != active), None)

        if not fallback:
            print("❌ 没有可用的备用参数组")
            return

        # 先切换到备用组
        cfg.set_active_profile(fallback)

        # ✅ 3. 删除原来的组
        ok = cfg.delete_profile(active)
        if not ok:
            print(f"❌ 删除失败: {active}")
            return

        # ✅ 4. 刷新 UI
        update_combo_box()
        on_profile_change(fallback)

        print(f"✅ 成功删除参数组: {active}，已切换到: {fallback}")

        if dpg.does_item_exist("status_text"):
            dpg.configure_item(
                "status_text",
                default_value=f"[成功] 已删除 '{active}'，当前: '{fallback}'",
                color=(52, 199, 89, 255)  # 绿色
            )

    except Exception as e:
        print(f"❌ 删除参数组失败: {active}, error={e}")
        if dpg.does_item_exist("status_text"):
            dpg.configure_item(
                "status_text",
                default_value=f"[错误] 删除失败: {str(e)}",
                color=(255, 59, 48, 255)
            )


# ---------------------------- 构建 UI ----------------------------
import gui.widgets.callbacks as cbs

def refresh_target_class_ids_checkboxes():
    cbs.IS_REFRESHING_TARGET_IDS_UI = True
    try:
        ids = cfg.get_config("TARGET_CLASS_IDS", [])
        if not isinstance(ids, list):
            ids = []
        s = set(int(x) for x in ids)

        for i in range(15):
            tag = f"target_id_cb_{i}"
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, i in s)
    finally:
        cbs.IS_REFRESHING_TARGET_IDS_UI = False

def build_features_tab(blue_notice_theme):
    with dpg.tab(label="功能参数"):
        dpg.add_text("参数组管理", color=UIColors.APPLE_BLUE)
        with dpg.group(horizontal=True):
            dpg.add_text("创建新的参数组:", color=UIColors.TEXT_GRAY)
            dpg.add_input_text(tag="new_profile_name", width=200)
            dpg.add_button(label="新建参数组", small=True, callback=lambda: create_new_profile())


        with dpg.group(horizontal=True):
            dpg.add_text("当前选中要编辑的参数组:", color=UIColors.TEXT_GRAY)
            active_profile = cfg.get_active_profile()
            profile_names = cfg.list_profiles()

            dpg.add_combo(
                items=profile_names,
                default_value=active_profile,
                width=200,
                callback=lambda s, a: on_profile_change(a),
                tag="profile_combo_box"
            )

            dpg.add_button(label="删除参数组", small=True, callback=lambda: delete_profile_ui())
        dpg.add_text(
            "参数组包含：准星检测/视觉识别/PID控制/目标追踪/压强配置/自动开火\n"
            "比如我要新创建一个叫aw的参数，并绑定到右键\n"
            "第一步：在创建新的参数组输入框中输入AW，\n"
            "然后调整好PID等参数点击保存所有配置"
            "然后回到按键策略界面中，在RIGHT下面绑定参数组下拉框选中AW\n"
            "按键模式设置按住生效，勾选触发逻辑。\n"
            "这样一个参数组就设置好了，在游戏中长按右键就会使用叫AW的参数组\n"
            ,
            color=UIColors.TEXT_GRAY
        )
        dpg.add_separator()

        # ----------------- 下面保持你原来的 TAB 内容即可 -----------------
        with dpg.tab_bar():
            with dpg.tab(label="准星检测"):
                dpg.add_text("准星检测系统", color=UIColors.APPLE_BLUE)

                crosshair_deps = [
                    "crosshair_detector_type",
                    "crosshair_valorant_config",
                    "crosshair_preview_btn",
                    "crosshair_template_path",
                    "crosshair_use_fallback",
                    "crosshair_debug_mode",
                    "crosshair_stats_interval",
                    "crosshair_search_x_left",
                    "crosshair_search_x_right",
                    "crosshair_search_y_up",
                    "crosshair_search_y_down",
                    "crosshair_smooth_factor",
                    "crosshair_max_lost_frames"
                ]

                # ✅ 使用 add_bool_tagged + 自定义 callback
                add_bool_tagged(
                    "ENABLE_CROSSHAIR_DETECTION",
                    "启用准星检测",
                    "enable_crosshair",
                    callback=lambda s, a, u: update_dependent_controls(
                        "ENABLE_CROSSHAIR_DETECTION",
                        crosshair_deps,
                        a
                    )
                )

                dpg.add_separator()
                dpg.add_text("检测器配置", color=UIColors.SECTION_HEADER)

                add_combo_tagged(
                    "CROSSHAIR_DETECTOR_TYPE",
                    "检测器类型",
                    ["color", "template", "cross_shape", "red_dot"],
                    "crosshair_detector_type"
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("如果你是三角洲用户，就点击下拉框选择red_dot\n"
                                 "如果使用red_dot的话，那你的激光不可以同样使用红色的，会对准星锁造成干扰\n"
                                 "其他模式较为复杂，我后面会出详细的使用方法。\n"
                                 )
                dpg.add_text("说明: color=颜色匹配 | template=模板匹配 | cross_shape=十字形状检测",
                             color=UIColors.TEXT_GRAY, indent=20)

                dpg.add_separator()
                dpg.add_text("Valorant 准星配置", color=UIColors.SECTION_HEADER)

                add_input_text_tagged(
                    "CROSSHAIR_VALORANT_CONFIG",
                    "准星代码",
                    "crosshair_valorant_config"
                )

                dpg.add_text("示例: 0;P;c;5;o;1;d;1;0t;1;0l;2;0o;2;0a;1;0f;0;1b;0",
                             color=UIColors.TEXT_GRAY, indent=20)

                dpg.add_button(
                    label="生成预览",
                    callback=generate_crosshair_preview_callback,
                    width=200,
                    height=30,
                    tag="crosshair_preview_btn"
                )

                dpg.add_separator()
                dpg.add_text("准星预览", color=UIColors.APPLE_BLUE)

                # ⭐ 使用 child_window 包裹图像
                with dpg.child_window(width=110, height=110, border=True):
                    dpg.add_image(
                        "crosshair_preview_texture",
                        width=90,
                        height=90,
                        tag="crosshair_preview_image"
                    )

                dpg.add_text("准星描述: 未生成", tag="crosshair_preview_desc", color=UIColors.TEXT_GRAY)

                dpg.add_text("外部模板配置", color=UIColors.SECTION_HEADER)

                add_input_text_tagged(
                    "CROSSHAIR_TEMPLATE_PATH",
                    "模板图片路径",
                    "crosshair_template_path"
                )

                dpg.add_text("说明:用于 template 模式,支持相对/绝对路径",
                             color=UIColors.TEXT_GRAY, indent=20)

                dpg.add_separator()
                dpg.add_text("高级选项", color=UIColors.SECTION_HEADER)

                add_bool_tagged(
                    "CROSSHAIR_USE_FALLBACK_CENTER",
                    "检测失败时使用屏幕中心",
                    "crosshair_use_fallback"
                )

                add_bool_tagged(
                    "CROSSHAIR_DEBUG_MODE",
                    "启用调试模式（详细日志）",
                    "crosshair_debug_mode"
                )

                add_int_tagged(
                    "CROSSHAIR_STATS_INTERVAL",
                    "统计输出间隔（秒）",
                    60, 1800,
                    "crosshair_stats_interval"
                )
                dpg.add_separator()
                dpg.add_text("搜索区域配置（长方形，针对后坐力优化）", color=UIColors.SECTION_HEADER)

                dpg.add_text(
                    "说明：准星在开枪时会因后坐力向上偏移，使用长方形搜索区域可提升检测效率",
                    color=UIColors.TEXT_GRAY,
                    wrap=400
                )

                # 获取当前配置
                bounds = cfg.get_config("CROSSHAIR_SEARCH_BOUNDS", {
                    "x_left": -30,
                    "x_right": 30,
                    "y_up": -150,
                    "y_down": 20
                })

                # 水平方向
                dpg.add_text("水平搜索范围 (X轴)", color=UIColors.TEXT_GRAY, indent=10)
                dpg.add_input_int(
                    label="向左搜索（负数）",
                    default_value=bounds.get("x_left", -30),
                    tag="crosshair_search_x_left",
                    step=0,
                    width=280,
                    callback=lambda s, a: update_search_bounds("x_left", a)
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("从屏幕中心向左的搜索距离（像素）\n建议: -20 到 -50")

                dpg.add_input_int(
                    label="向右搜索（正数）",
                    default_value=bounds.get("x_right", 30),
                    tag="crosshair_search_x_right",
                    step=0,
                    width=280,
                    callback=lambda s, a: update_search_bounds("x_right", a)
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("从屏幕中心向右的搜索距离（像素）\n建议: 20 到 50")

                # 垂直方向
                dpg.add_text("垂直搜索范围 (Y轴)", color=UIColors.TEXT_GRAY, indent=10)
                dpg.add_input_int(
                    label="向上搜索（负数）",
                    default_value=bounds.get("y_up", -150),
                    tag="crosshair_search_y_up",
                    step=0,
                    width=280,
                    callback=lambda s, a: update_search_bounds("y_up", a)
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("从屏幕中心向上的搜索距离（像素）\n后坐力主要方向，建议: -100 到 -200")

                dpg.add_input_int(
                    label="向下搜索（正数）",
                    default_value=bounds.get("y_down", 20),
                    tag="crosshair_search_y_down",
                    step=0,
                    width=280,
                    callback=lambda s, a: update_search_bounds("y_down", a)
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("从屏幕中心向下的搜索距离（像素）\n准星很少向下移动，建议: 10 到 30")

                # 显示当前搜索区域大小
                current_width = bounds.get("x_right", 30) - bounds.get("x_left", -30)
                current_height = abs(bounds.get("y_up", -150)) + bounds.get("y_down", 20)
                dpg.add_text(
                    f"当前搜索区域: {current_width}×{current_height} 像素",
                    tag="crosshair_search_area_display",
                    color=UIColors.SUCCESS_GREEN,
                    indent=10
                )
                dpg.add_separator()
                dpg.add_text("平滑与容错配置", color=UIColors.SECTION_HEADER)

                add_float_input_tagged(
                    "CROSSHAIR_SMOOTH_FACTOR",
                    "位置平滑系数 (0=无平滑, 1=最大平滑)",
                    "crosshair_smooth_factor",
                    format="%.2f"
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("值越小，准星位置变化越平滑\n建议: 0.2 - 0.5\n设为 1 可禁用平滑")

                add_int_input_tagged(
                    "CROSSHAIR_MAX_LOST_FRAMES",
                    "最大丢失帧数（容错）",
                    "crosshair_max_lost_frames"
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("连续检测失败多少帧后才使用屏幕中心\n建议: 3 - 10 帧")

                dpg.add_separator()

            # ================= TAB 5: 视觉识别 =================
            with dpg.tab(label="视觉识别"):
                dpg.add_text("检测参数", color=UIColors.APPLE_BLUE)
                add_float("CONF_THRESHOLD", "置信度阈值", 0.1, 0.99)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("置信度越高，程序越‘挑剔’。如果发现准星经常锁定在墙壁、草地等非目标物体上（锁环境），请调高此值。\n"
                                 "如果调的很高比如0.6还是锁环境，那就说明你使用的onnx模型比较垃圾换一个。\n"
                                 )
                add_float("IOU_THRESHOLD", "重叠剔除 (IOU)", 0.1, 0.99)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("如果你发现准星经常在同一个目标身上反复横跳，可以尝试稍微调低一点点（如 0.45）\n"
                                 "如果你发现两个敌人走在一起时，其中一个人的框经常消失，可以尝试稍微调高一点点（如 0.55）\n"
                                 )
                dpg.add_separator()
                dpg.add_text("目标 ID 选择", color=UIColors.APPLE_BLUE)

                current_ids = cfg.get_config("TARGET_CLASS_IDS", [])
                with dpg.table(header_row=False, borders_innerH=False, borders_outerH=False,
                               borders_innerV=False, borders_outerV=False):

                    # 添加8列
                    for _ in range(8):
                        dpg.add_table_column()

                    # 添加2行（15个ID需要2行）
                    for row in range(2):
                        with dpg.table_row():
                            for col in range(8):
                                i = row * 8 + col
                                if i < 15:
                                    is_active = i in current_ids
                                    dpg.add_checkbox(
                                        label=f"ID {i}",
                                        tag=f"target_id_cb_{i}",
                                        default_value=is_active,
                                        callback=update_class_ids_callback,
                                        user_data=i
                                    )
                                else:
                                    dpg.add_text("")  # 空占位

                dpg.add_separator()
                dpg.add_text("头部优先策略", color=UIColors.SECTION_HEADER)

                head_priority_deps = [
                    "body_class_id",
                    "head_class_id",
                    "head_priority_range",
                    "ignore_small_head",
                    "small_target_threshold"
                ]
                add_bool_tagged(
                    "ENABLE_HEAD_PRIORITY",
                    "启用头部优先",
                    tag="enable_head_priority",
                    callback=lambda s, a, u: update_dependent_controls(
                        "ENABLE_HEAD_PRIORITY",
                        head_priority_deps,
                        a
                    )
                )
                add_int_tagged("BODY_CLASS_ID", "身体 ID 定义", 0, 15, "body_class_id")
                add_int_tagged("HEAD_CLASS_ID", "头部 ID 定义", 0, 15, "head_class_id")
                add_int_tagged("HEAD_PRIORITY_RANGE", "头部优先距离范围 (像素)", 0, 500, "head_priority_range")
                dpg.add_text("说明:在目标组内,头部可以比最近检测框远多少像素",
                             color=UIColors.TEXT_GRAY)

                dpg.add_separator()
                dpg.add_text("小目标头部过滤 (新增)", color=UIColors.SECTION_HEADER)

                small_target_deps = ["small_target_threshold"]

                add_bool_tagged(
                    "IGNORE_SMALL_TARGET_HEAD",
                    "忽略小目标的头部检测框",
                    tag="ignore_small_head",
                    callback=lambda s, a, u: update_dependent_controls(
                        "IGNORE_SMALL_TARGET_HEAD",
                        small_target_deps,
                        a
                    )
                )

                add_int_tagged("SMALL_TARGET_AREA_THRESHOLD", "小目标尺寸阈值 (像素)", 10, 1000,
                               "small_target_threshold")

                dpg.add_text("说明:当检测框宽度或高度 < 此值时,忽略头部类别",
                             color=UIColors.TEXT_GRAY)
                dpg.add_text("适用场景:远距离目标 / 头部抖动严重时",
                             color=UIColors.TEXT_GRAY)

                update_dependent_controls(
                    "ENABLE_HEAD_PRIORITY",
                    head_priority_deps,
                    cfg.get_config("ENABLE_HEAD_PRIORITY", True)
                )
                update_dependent_controls(
                    "IGNORE_SMALL_TARGET_HEAD",
                    small_target_deps,
                    cfg.get_config("IGNORE_SMALL_TARGET_HEAD", True)
                )

            # ================= TAB 6: PID 瞄准 =================
            with dpg.tab(label="PID 控制"):
                # 上部分：参数设置
                dpg.add_text("瞄准偏移参数", color=UIColors.APPLE_BLUE)
                with dpg.group(horizontal=False):
                    add_float_input_tagged(
                        "AIM_Y_RATIO",
                        "Y轴 瞄准高度",
                        tag="input_aim_y",
                        format="%.3f",
                        callback=lambda s, a, u: update_aim_offset_preview()  # ✅ 添加预览更新
                    )

                    add_float_input_tagged(
                        "AIM_X_OFFSET",
                        "X轴 微调偏移",
                        tag="input_aim_x",
                        format="%.3f",
                        callback=lambda s, a, u: update_aim_offset_preview()  # ✅ 添加预览更新
                    )

                # 中部分：预览面板 (放在参数下方)

                dpg.add_text("实时瞄准位置预览", color=UIColors.APPLE_BLUE)
                with dpg.group(horizontal=True):
                    with dpg.child_window(width=300, height=180, border=True, no_scrollbar=True):
                        with dpg.group(horizontal=True):
                            # 绘制区
                            with dpg.drawlist(width=100, height=160, tag="aim_preview_drawlist"):
                                dpg.add_draw_node(tag="aim_preview_node")
                            dpg.bind_item_handler_registry("aim_preview_drawlist", "preview_handler")
                            # 右侧说明文字
                            with dpg.group():
                                dpg.add_spacer(height=40)
                                dpg.add_text("支持鼠标直接拖拽圆点", color=UIColors.SUCCESS_GREEN)  # 提示用户
                                dpg.add_text("调整结果将自动同步", color=UIColors.TEXT_GRAY)

                dpg.add_separator()
                dpg.add_text("PID 参数 (X 横向)", color=UIColors.SECTION_HEADER)
                add_float("PID_KP_X", "P (比例-速度)", 0.0, 5.0, speed=0.01)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "横向吸力\n控制准星左右移动的爆发力。\n数值越大，左右锁人的瞬移感越强。\n如果你觉得准星跟不上左右跑的人，就调大它。")
                add_float("PID_KI_X", "I (积分-误差)", 0.0, 2.0, speed=0.001)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "横向修正\n如果你的枪线总是追着目标屁股跑，那就增加这个值每次增加0.01。\n调大此值会导致准星左右乱飞。")
                add_float("PID_KD_X", "D (微分-阻尼)", 0.0, 1.0, speed=0.001)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "横向减震\n消除准星左右锁定时的‘颤抖’。\n如果准星吸到人后左右高频抖动，就调大这个值。")
                dpg.add_separator()
                dpg.add_text("PID 参数 (Y 纵向)", color=UIColors.SECTION_HEADER)
                add_float("PID_KP_Y", "P (比例-速度)", 0.0, 5.0, speed=0.01)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "纵向吸力\n控制准星上下移动的爆发力。\n如果你觉得准星‘压不住’或者‘抬不起来’，调大它。")
                add_float("PID_KI_Y", "I (积分-误差)", 0.0, 2.0, speed=0.001)
                add_float("PID_KD_Y", "D (微分-阻尼)", 0.0, 1.0, speed=0.001)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "纵向减震\n防止准星在敌人头顶和脚底之间来回跳动。\n配合压枪使用时，较大的 D 能让下压过程更平滑。")
                dpg.add_separator()
                dpg.add_text("限制与死区", color=UIColors.SECTION_HEADER)
                add_int("MAX_SINGLE_MOVE_PX", "单帧最大移动像素", 1, 2000)
                add_int("PRECISION_DEAD_ZONE", "瞄准死区 (像素)", 0, 50)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("在这个像素范围内，准星不会再微调。\n"
                                 "设为 2 到 5 可以有效消除准星在锁定目标时的‘微颤’感。")
                add_int("DEFAULT_DELAY_MS_PER_STEP", "每步延迟 (ms)", 0, 50)

            # ================= TAB 7: 目标追踪 =================
            with dpg.tab(label="目标追踪"):
                dpg.add_text("目标分组设置", color=UIColors.APPLE_BLUE)
                add_int("TARGET_GROUP_DISTANCE_THRESHOLD", "身体头部分组距离阈值", 10, 500)

                dpg.add_text("说明：身体和头部距离小于此值时认为是同一个目标",
                             color=UIColors.TEXT_GRAY)

                dpg.add_separator()
                dpg.add_text("目标选择与锁定", color=UIColors.SECTION_HEADER)
                add_int("MIN_TARGET_LOCK_FRAMES", "最小锁定帧数", 1, 100)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "锁定一个目标后,至少要追踪这么多帧才允许切换到其他目标。\n"
                        "作用: 防止准星在两个敌人之间来回横跳。\n"
                        "例子:\n"
                        "设为 10: 锁定后会稳定追踪至少 10 帧(约 0.16 秒)。\n"
                        "设为 30: 更稳定,但如果旁边突然出现更近的敌人,反应会慢一点。\n"
                        "设为 1: 几乎不锁定,准星会疯狂在多个目标间跳动。"
                    )
                add_int("TARGET_SWITCH_DISTANCE_THRESHOLD", "切换距离阈值 (像素)", 10, 500)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "当前锁定的目标和新目标的距离差要超过这个值,才会考虑切换。\n"
                        "例子:\n"
                        "  设为 50: 只有新目标比当前目标近 50 像素以上,才会切换。\n"
                        "  设为 10: 非常敏感,稍微有更近的目标就会切换。\n"
                        "  设为 200: 非常保守,除非新目标明显更近,否则不切换。\n"
                        "建议: 配合'最小锁定帧数'一起调,两者共同决定锁定的稳定性。"
                    )

                add_int("TARGET_IDENTITY_DISTANCE", "同目标判定距离 (像素)", 10, 500)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "如果这一帧的目标和上一帧的目标距离小于这个值,就认为是同一个人。\n"
                        "作用: 防止敌人移动时被当成'新目标',导致锁定重置。\n"
                        "例子:\n"
                        "  设为 100: 适合大部分情况,敌人正常移动不会丢失追踪。\n"
                        "  设为 50: 如果敌人移动速度很快(比如滑铲、冲刺),可能会被当成新目标。\n"
                        "  设为 200: 即使敌人瞬移也能保持追踪,但可能把两个不同的人当成同一个。"
                    )
                add_int("MAX_LOST_FRAMES", "丢失目标容忍帧", 1, 300)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "当目标消失(比如躲到掩体后)时,程序会继续'记住'这个目标多少帧。\n"
                        "作用: 防止敌人短暂消失后,准星就完全重置了。\n"
                        "例子:\n"
                        "  设为 30: 目标消失 0.5 秒内重新出现,准星会继续锁定。\n"
                        "  设为 60: 目标消失 1 秒内重新出现,准星会继续锁定。\n"
                        "  设为 5: 目标稍微被遮挡就会丢失,需要重新锁定。\n"
                        "建议: 30-60 帧(0.5-1 秒)"
                    )

                dpg.add_separator()
                dpg.add_text("卡尔曼滤波 (Kalman)", color=UIColors.SECTION_HEADER)

                kalman_deps = ["kalman_process", "kalman_measure", "kalman_predict"]
                add_bool_tagged(
                    "USE_KALMAN_FILTER",
                    "启用卡尔曼滤波",
                    tag="use_kalman_filter",
                    callback=lambda s, a, u: update_dependent_controls(
                        "USE_KALMAN_FILTER",
                        kalman_deps,
                        a
                    )
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "卡尔曼滤波是一种'预测算法',能让准星更平滑地追踪移动目标。\n"
                        "作用:\n"
                        "  1. 消除检测框的抖动(模型识别不稳定时)。\n"
                        "  2. 预测目标的移动方向,提前瞄准。\n"
                        "  3. 当目标短暂消失时,继续预测位置。\n"
                        "建议: 保持开启(默认)"
                    )
                add_float_tagged("KALMAN_PROCESS_NOISE", "过程噪声", 0.01, 10.0, "kalman_process")
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "数值越大,卡尔曼越相信'目标会突然变向',追踪会更灵活但也更抖。\n"
                        "例子:\n"
                        "  0.1: 适合匀速移动的目标(比如走路的敌人)。\n"
                        "  0.5: 适合经常变向的目标(比如左右晃动的敌人)。\n"
                        "  5.0: 目标移动非常不规律,但准星会变得不稳定。\n"
                    )
                add_float_tagged("KALMAN_MEASUREMENT_NOISE", "测量噪声", 0.1, 50.0, "kalman_measure")
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "数值越大,卡尔曼越不相信模型给出的位置,会更依赖自己的预测。\n"
                        "例子:\n"
                        "  1.0: 非常相信模型,准星会紧跟检测框(可能会抖)。\n"
                        "  5.0: 适度平滑,既跟得上又不抖。\n"
                        "  20.0: 非常平滑,但如果目标突然变向,准星反应会慢。\n"
                    )
                add_int_tagged("KALMAN_MAX_PREDICT_FRAMES", "最大预测帧数", 0, 60, "kalman_predict")
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "当目标消失时,卡尔曼最多预测多少帧的位置。\n"
                        "例子:\n"
                        "  3: 目标消失 0.05 秒内,准星会继续预测移动。\n"
                        "  10: 目标消失 0.16 秒内,准星会继续预测移动。\n"
                        "  0: 目标一消失,准星立刻停止移动。\n"
                    )
                update_dependent_controls(
                    "USE_KALMAN_FILTER",
                    kalman_deps,
                    cfg.get_config("USE_KALMAN_FILTER", True)
                )
                dpg.add_separator()
                dpg.add_text("EMA 平滑 (备用)", color=UIColors.SECTION_HEADER)
                add_float("AIM_POINT_SMOOTH_ALPHA", "瞄准点平滑系数 (仅在禁用卡尔曼时生效)", 0.01, 1.0)
                dpg.add_separator()
                dpg.add_text("移动预判", color=UIColors.SECTION_HEADER)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "【简易平滑】\n"
                        "当你关闭卡尔曼滤波时,这个参数会生效。\n"
                        "作用: 让准星不要直接跳到目标位置,而是'滑'过去。\n"
                        "例子:\n"
                        "  0.1: 非常平滑,但准星会明显'拖尾'。\n"
                        "  0.5: 平衡,既平滑又不会太慢。\n"
                        "  1.0: 不平滑,准星直接跳到目标位置(会抖)。\n"
                    )
                lead_deps = ["lead_frames"]
                add_bool_tagged(
                    "ENABLE_LEAD_TARGET",
                    "启用移动预判",
                    tag="enable_lead_target",
                    callback=lambda s, a, u: update_dependent_controls(
                        "ENABLE_LEAD_TARGET",
                        lead_deps,
                        a
                    )
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "根据目标的移动速度,预测他未来的位置,提前瞄准。\n"
                    )
                add_int_tagged("LEAD_FRAMES", "预判提前量 (帧)", 0, 30, "lead_frames")
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "根据目标当前速度,预测他 N 帧后的位置。\n"
                        "  2: 预测 0.03 秒后的位置(适合近距离)。\n"
                        "  5: 预测 0.08 秒后的位置(适合中距离)。\n"
                        "  0: 预测 0.16 秒后的位置(适合远距离狙击)。\n"
                    )
                update_dependent_controls(
                    "ENABLE_LEAD_TARGET",
                    lead_deps,
                    cfg.get_config("ENABLE_LEAD_TARGET", False)
                )
            # ================= TAB 8: 压枪系统 =================
            with dpg.tab(label="压枪配置"):
                dpg.add_text("总开关", color=UIColors.APPLE_BLUE)

                recoil_deps = [
                    "recoil_ctrl", "recoil_mode", "recoil_req_target", "recoil_req_lock",
                    "recoil_timeout", "recoil_lock_frames", "recoil_pattern", "recoil_v_speed",
                    "recoil_h_speed", "recoil_inc_y", "recoil_h_var", "recoil_max_move",
                    "recoil_max_x", "recoil_max_y"
                ]
                add_bool_tagged(
                    "ENABLE_MANUAL_RECOIL",
                    "启用压枪系统",
                    tag="enable_manual_recoil",
                    callback=lambda s, a, u: update_dependent_controls(
                        "ENABLE_MANUAL_RECOIL",
                        recoil_deps,
                        a
                    )
                )
                add_bool_tagged("ENABLE_RECOIL_CONTROL", "启用后坐力控制", "recoil_ctrl")
                add_combo_tagged("MANUAL_RECOIL_TRIGGER_MODE", "触发按键模式",
                                 ["left_only", "left_right", "left_button4", "left_button5"], "recoil_mode")
                dpg.add_separator()
                dpg.add_text("触发逻辑", color=UIColors.SECTION_HEADER)
                add_bool_tagged("RECOIL_REQUIRE_TARGET", "仅在有目标时压枪", "recoil_req_target")
                add_bool_tagged("RECOIL_REQUIRE_LOCK", "仅在锁定目标时压枪", "recoil_req_lock")
                add_float_tagged("RECOIL_TARGET_TIMEOUT", "目标丢失超时 (秒)", 0.1, 5.0, "recoil_timeout")
                add_int_tagged("RECOIL_MIN_LOCK_FRAMES", "压枪前需锁定帧数", 0, 100, "recoil_lock_frames")

                dpg.add_separator()
                dpg.add_text("压枪参数", color=UIColors.SECTION_HEADER)
                add_combo_tagged("RECOIL_PATTERN", "压枪模式",
                                 ["linear", "exponential", "custom"], "recoil_pattern")
                add_float_tagged("RECOIL_VERTICAL_SPEED", "垂直下压速度", 0.0, 1000.0, "recoil_v_speed")
                add_float_tagged("RECOIL_HORIZONTAL_SPEED", "水平修正速度", -500.0, 500.0, "recoil_h_speed")
                add_float_tagged("RECOIL_INCREMENT_Y", "纵向递增系数", 0.0, 10.0, "recoil_inc_y")
                add_int_tagged("RECOIL_HORIZONTAL_VARIANCE", "水平随机抖动", 0, 50, "recoil_h_var")

                dpg.add_separator()
                dpg.add_text("安全限制", color=UIColors.SECTION_HEADER)
                add_float_tagged("RECOIL_MAX_SINGLE_MOVE", "单次最大合力", 1.0, 500.0, "recoil_max_move")
                add_float_tagged("RECOIL_MAX_SINGLE_MOVE_X", "X轴 最大单次", 1.0, 200.0, "recoil_max_x")
                add_float_tagged("RECOIL_MAX_SINGLE_MOVE_Y", "Y轴 最大单次", 1.0, 200.0, "recoil_max_y")

                update_dependent_controls(
                    "ENABLE_MANUAL_RECOIL",
                    recoil_deps,
                    cfg.get_config("ENABLE_MANUAL_RECOIL", True)
                )

            # ================= TAB 9: 自动开火 =================
            with dpg.tab(label="自动开火"):

                autofire_deps = ["autofire_debug", "autofire_acc", "autofire_dist", "autofire_lock"]
                add_bool_tagged(
                    "ENABLE_AUTO_FIRE",
                    "启用自动开火",
                    tag="enable_auto_fire",
                    callback=lambda s, a, u: update_dependent_controls(
                        "ENABLE_AUTO_FIRE",
                        autofire_deps,
                        a
                    )
                )

                add_bool_tagged("AUTO_FIRE_DEBUG_MODE", "自动开火调试", "autofire_debug")

                dpg.add_separator()
                dpg.add_text("触发阈值", color=UIColors.ERROR_RED)  # 保持醒目，但稍微调暗
                add_float_tagged("AUTO_FIRE_ACCURACY_THRESHOLD", "准星重合度 (0.1-1.0)",
                                 0.1, 1.0, "autofire_acc")
                add_float_tagged("AUTO_FIRE_DISTANCE_THRESHOLD", "距离像素阈值",
                                 1.0, 200.0, "autofire_dist")
                add_int_tagged("AUTO_FIRE_MIN_LOCK_FRAMES", "开火前需锁定帧数",
                               0, 100, "autofire_lock")
                update_dependent_controls(
                    "ENABLE_AUTO_FIRE",
                    autofire_deps,
                    cfg.get_config("ENABLE_AUTO_FIRE", False)
                )
