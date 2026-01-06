import threading
import dearpygui.dearpygui as dpg
import config_manager as cfg
import os
import glob
import cv2
import numpy as np

# 1. 加载配置
cfg.load_config()

# ========== 全局退出信号 ==========
_gui_exit_event = threading.Event()
_gui_running = False

# 脚本文件夹路径
SCRIPTS_DIR = "scripts"


# ========== 🎨 UI 颜色配置 (适配白色背景) ==========
class UIColors:
    TEXT_BLACK = (0, 0, 0, 255)
    TEXT_GRAY = (100, 100, 100, 255)
    APPLE_BLUE = (0, 122, 255, 255)  # 标题/强调色
    SUCCESS_GREEN = (52, 199, 89, 255)  # 成功状态
    WARNING_ORANGE = (255, 149, 0, 255)  # 警告/未保存
    ERROR_RED = (255, 59, 48, 255)  # 错误
    SECTION_HEADER = (0, 122, 255, 255)  # 分区标题颜色


# ================= 控件联动管理 =================

def update_dependent_controls(master_key, dependent_tags, is_enabled):
    """通用函数：根据主开关状态启用/禁用子控件"""
    for tag in dependent_tags:
        try:
            dpg.configure_item(tag, enabled=is_enabled)
        except Exception as e:
            print(f"[GUI] 无法更新控件 {tag}: {e}")


def create_master_switch_callback(config_key, dependent_tags):
    """创建带联动的主开关回调函数"""

    def callback(sender, app_data, user_data):
        # 更新配置
        cfg.set_config(config_key, app_data)
        dpg.configure_item("status_text", default_value=f"[未保存] 已修改: {config_key}", color=UIColors.WARNING_ORANGE)

        # 更新子控件状态
        update_dependent_controls(config_key, dependent_tags, app_data)

    return callback


# ================= 原有回调函数 =================

def save_callback():
    """保存配置"""
    if cfg.save_config():
        dpg.configure_item("status_text", default_value="[成功] 配置已保存至 config.json", color=UIColors.SUCCESS_GREEN)
    else:
        dpg.configure_item("status_text", default_value="[错误] 保存失败！请检查权限", color=UIColors.ERROR_RED)


def update_config_callback(sender, app_data, user_data):
    """通用单值更新回调"""
    key = user_data
    value = app_data
    cfg.set_config(key, value)
    dpg.configure_item("status_text", default_value=f"[未保存] 已修改: {key}", color=UIColors.WARNING_ORANGE)


def update_class_ids_callback(sender, app_data, user_data):
    """处理目标ID多选"""
    target_id = user_data
    is_checked = app_data
    current_ids = cfg.get_config("TARGET_CLASS_IDS", [])
    if not isinstance(current_ids, list): current_ids = []

    if is_checked:
        if target_id not in current_ids: current_ids.append(target_id)
    else:
        if target_id in current_ids: current_ids.remove(target_id)

    current_ids.sort()
    cfg.set_config("TARGET_CLASS_IDS", current_ids)
    dpg.configure_item("status_text", default_value=f"[未保存] 目标ID更新: {current_ids}",
                       color=UIColors.WARNING_ORANGE)


# ================= 脚本管理逻辑 =================

def update_script_state_callback(sender, app_data, user_data):
    """处理脚本开关"""
    script_name = user_data
    is_enabled = app_data

    enabled_scripts = cfg.get_config("ENABLED_SCRIPTS", [])
    if not isinstance(enabled_scripts, list): enabled_scripts = []

    if is_enabled:
        if script_name not in enabled_scripts:
            enabled_scripts.append(script_name)
            print(f"[GUI] 启用脚本: {script_name}")
    else:
        if script_name in enabled_scripts:
            enabled_scripts.remove(script_name)
            print(f"[GUI] 禁用脚本: {script_name}")

    cfg.set_config("ENABLED_SCRIPTS", enabled_scripts)
    dpg.configure_item("status_text", default_value=f"[未保存] 脚本列表已更新", color=UIColors.WARNING_ORANGE)
    refresh_scripts_ui()


def refresh_scripts_ui():
    """扫描文件夹并重建脚本列表 UI"""
    dpg.delete_item("script_list_container", children_only=True)

    if not os.path.exists(SCRIPTS_DIR):
        os.makedirs(SCRIPTS_DIR)

    lua_files = glob.glob(os.path.join(SCRIPTS_DIR, "*.lua"))
    script_names = [os.path.splitext(os.path.basename(f))[0] for f in lua_files]
    enabled_scripts = cfg.get_config("ENABLED_SCRIPTS", [])

    if not script_names:
        dpg.add_text("未找到脚本文件 (请在 scripts/ 文件夹放入 .lua)", parent="script_list_container",
                     color=UIColors.TEXT_GRAY)
        return

    for name in script_names:
        is_active = name in enabled_scripts
        with dpg.group(horizontal=True, parent="script_list_container"):
            dpg.add_checkbox(
                label=f"{name}.lua",
                default_value=is_active,
                callback=update_script_state_callback,
                user_data=name
            )
            if is_active:
                dpg.add_text("(已启用)", color=UIColors.SUCCESS_GREEN)
            else:
                dpg.add_text("(未启用)", color=UIColors.TEXT_GRAY)


def generate_crosshair_preview_callback(sender, app_data, user_data):
    """生成准星预览回调"""
    try:
        config_code = cfg.get_config("CROSSHAIR_VALORANT_CONFIG", "").strip()

        if not config_code:
            dpg.configure_item("status_text", default_value="[错误] 请先填写准星代码", color=UIColors.ERROR_RED)
            return

        dpg.configure_item("status_text", default_value="[处理中] 正在生成...", color=UIColors.WARNING_ORANGE)

        from crosshair.games.valorant.config_parser import ValorantConfigParser
        from crosshair.games.valorant.crosshair_visualizer import CrosshairVisualizer

        # 解析配置
        config = ValorantConfigParser.parse(config_code)
        desc = ValorantConfigParser.describe(config)

        # 渲染
        template_img = CrosshairVisualizer.render(config, size=90)
        img_rgba = cv2.cvtColor(template_img, cv2.COLOR_BGRA2RGBA)

        # Alpha 混合到浅灰色背景 (适配白色UI)
        alpha = img_rgba[:, :, 3:4].astype(np.float32) / 255.0
        rgb = img_rgba[:, :, :3].astype(np.float32)
        # 背景色改为浅灰 (230, 230, 230)
        background = np.full((90, 90, 3), 230, dtype=np.float32)
        blended_rgb = rgb * alpha + background * (1 - alpha)

        # 重新组合
        final_rgba = np.concatenate([
            blended_rgb.astype(np.uint8),
            np.full((90, 90, 1), 255, dtype=np.uint8)
        ], axis=-1)

        # 转换为纹理数据并更新
        texture_data = (final_rgba.astype(np.float32) / 255.0).flatten().tolist()
        dpg.set_value("crosshair_preview_texture", texture_data)

        # 更新状态
        dpg.configure_item("crosshair_preview_desc", default_value=f"✅ {desc}", color=UIColors.SUCCESS_GREEN)
        dpg.configure_item("status_text", default_value="[成功] 准星预览已生成", color=UIColors.SUCCESS_GREEN)

    except ValueError as e:
        dpg.configure_item("crosshair_preview_desc", default_value="❌ 准星代码格式错误", color=UIColors.ERROR_RED)
        dpg.configure_item("status_text", default_value=f"[错误] 准星代码格式错误: {str(e)}", color=UIColors.ERROR_RED)

    except Exception as e:
        dpg.configure_item("crosshair_preview_desc", default_value="❌ 生成失败", color=UIColors.ERROR_RED)
        dpg.configure_item("status_text", default_value=f"[错误] {str(e)}", color=UIColors.ERROR_RED)
        import traceback
        traceback.print_exc()


# ================= 字体设置 =================

def setup_chinese_font():
    with dpg.font_registry():
        font_path = r"C:\Windows\Fonts\msyh.ttc"
        if not os.path.exists(font_path):
            font_path = r"C:\Windows\Fonts\simhei.ttf"

        if os.path.exists(font_path):
            # 加大字体一点点，配合 Apple 风格
            with dpg.font(font_path, 18) as font_cn:
                dpg.add_font_range(0x0020, 0x00FF)
                dpg.add_font_range(0x4E00, 0x9FA5)
            dpg.bind_font(font_cn)
        else:
            print("[GUI] ⚠ 未找到中文字体")


# ================= 🎨 Apple 风格主题设置 =================
# ================= 🎨 Apple 风格主题设置 (优化版) =================
def setup_apple_theme():
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            # --- 1. 形状与圆角 (保持圆润) ---
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 10, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 8, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 6, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 6, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize, 12, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, 12, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 10, 8, category=dpg.mvThemeCat_Core)

            # --- 2. 边框优化 ---
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 1, category=dpg.mvThemeCat_Core)  # 输入框描边

            # --- 3. 基础颜色 (White Mode) ---
            # 窗口与背景
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (255, 255, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (245, 245, 247), category=dpg.mvThemeCat_Core)
            # 🔥🔥🔥【关键修复】下拉框/菜单/提示框背景 🔥🔥🔥
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg, (255, 255, 255), category=dpg.mvThemeCat_Core)

            # 🔥🔥🔥【建议优化】下拉列表中条目的悬停/选中背景 🔥🔥🔥
            # 如果不加这个，鼠标指上去可能会变成默认的深蓝色，配合黑色文字会看不清
            dpg.add_theme_color(dpg.mvThemeCol_Header, (242, 242, 247), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (229, 229, 234), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (209, 209, 214), category=dpg.mvThemeCat_Core)
            # 文字：深炭灰 (比纯黑更柔和)
            dpg.add_theme_color(dpg.mvThemeCol_Text, (28, 28, 30), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, (142, 142, 147), category=dpg.mvThemeCat_Core)

            # 边框：中性灰
            dpg.add_theme_color(dpg.mvThemeCol_Border, (200, 200, 200), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_BorderShadow, (0, 0, 0, 0), category=dpg.mvThemeCat_Core)

            # 按钮
            dpg.add_theme_color(dpg.mvThemeCol_Button, (242, 242, 247), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (229, 229, 234), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (209, 209, 214), category=dpg.mvThemeCat_Core)

            # 输入框
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (255, 255, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (250, 250, 250), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (235, 235, 240), category=dpg.mvThemeCat_Core)

            # 控件强调色 (Slider, Checkbox)
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (0, 122, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (0, 122, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (0, 99, 209), category=dpg.mvThemeCat_Core)

            # 🔥🔥🔥 Tab 标签页配色 (关键修改) 🔥🔥🔥
            # 1. 未选中：浅灰 (保持背景感)
            dpg.add_theme_color(dpg.mvThemeCol_Tab, (242, 242, 247), category=dpg.mvThemeCat_Core)

            # 2. 悬停：稍白一点 (交互反馈)
            dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (250, 250, 250), category=dpg.mvThemeCat_Core)

            # 3. 选中：浅天蓝色 (适配深色字体)
            # 这里使用了 (215, 230, 255)，这是非常舒服的 macOS 风格浅蓝
            dpg.add_theme_color(dpg.mvThemeCol_TabActive, (215, 230, 255), category=dpg.mvThemeCat_Core)

            # 4. 失去焦点的选中项：保持浅蓝但淡一点
            dpg.add_theme_color(dpg.mvThemeCol_TabUnfocusedActive, (230, 240, 255), category=dpg.mvThemeCat_Core)

            # 滚动条
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, (255, 255, 255, 0), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, (199, 199, 204), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, (174, 174, 178), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, (142, 142, 147), category=dpg.mvThemeCat_Core)

    dpg.bind_theme(global_theme)


# ================= 主 GUI 创建 =================

def create_gui():
    dpg.create_context()

    # 1. 设置字体
    setup_chinese_font()
    # 2. 应用 Apple 风格主题
    setup_apple_theme()

    # 注册纹理
    with dpg.texture_registry():
        default_texture = []
        for y in range(90):
            for x in range(90):
                # 浅灰色背景适配白色主题
                default_texture.extend([0.9, 0.9, 0.9, 1.0])

        dpg.add_dynamic_texture(
            width=90,
            height=90,
            default_value=default_texture,
            tag="crosshair_preview_texture"
        )

    with dpg.window(tag="Primary Window", label="AI Config Ultimate v6.0 (Apple UI Edition)"):

        # === 顶部状态栏 ===
        with dpg.group(horizontal=True):
            dpg.add_button(label="保存所有配置 (Save)", callback=save_callback, height=30, width=160)
            dpg.add_text("[就绪]", tag="status_text", color=UIColors.TEXT_GRAY)

        dpg.add_separator()

        with dpg.tab_bar():

            # ================= TAB 1: 基础设置 =================
            with dpg.tab(label="基础 & 系统"):
                dpg.add_text("核心配置", color=UIColors.APPLE_BLUE)
                add_input_text("LICENSE_KEY", "许可证密钥 (License)")
                add_input_text("MODEL_PATH", "YOLO 模型路径")

                dpg.add_separator()
                dpg.add_text("系统性能", color=UIColors.APPLE_BLUE)
                add_bool("ENABLE_LOGGING", "启用日志记录")
                add_combo("LOG_LEVEL", "日志等级", ["DEBUG", "INFO", "WARNING", "ERROR"])
                add_bool("DEBUG_MODE", "调试模式 (显示画框)")
                add_bool("MAKCU_DEBUG_MODE", "Makcu调试模式")
                add_int("CAPTURE_FPS", "截图帧率限制", 1, 500)
                add_int("INFERENCE_FPS", "推理帧率限制", 1, 500)
                add_int("CONFIG_MONITOR_INTERVAL_SEC", "配置热重载间隔 (秒)", 1, 60)

            # ================= TAB 2: 图像源配置 =================
            with dpg.tab(label="图像源"):
                dpg.add_text("画面来源模式（需要重启启动）", color=UIColors.APPLE_BLUE)
                add_combo("IMAGE_SOURCE_TYPE", "图像源类型", ["local", "network"])
                add_int("CROP_SIZE", "推理区域大小 (Crop)", 64, 1280)

                dpg.add_separator()
                dpg.add_text("网络画面接收配置（需要重启启动） (仅network模式生效)", color=UIColors.SECTION_HEADER)
                add_int("FRAME_PORT", "接收端口", 1024, 65535)
                add_int("FRAME_WIDTH", "画面宽度 (像素)", 64, 1920)
                add_int("FRAME_HEIGHT", "画面高度 (像素)", 64, 1080)
                add_int("FRAME_CHANNELS", "通道数 (RGB=3, RGBA=4)", 3, 4)
                add_bool("USE_LZ4", "启用 LZ4 压缩传输")

            # ================= TAB 3: 准星检测 =================
            with dpg.tab(label="准星检测"):
                dpg.add_text("准星检测系统", color=UIColors.APPLE_BLUE)

                # 主开关（带联动）
                crosshair_deps = [
                    "crosshair_detector_type",
                    "crosshair_valorant_config",
                    "crosshair_preview_btn",
                    "crosshair_template_path",
                    "crosshair_use_fallback",
                    "crosshair_debug_mode",
                    "crosshair_stats_interval"
                ]
                crosshair_enabled = cfg.get_config("ENABLE_CROSSHAIR_DETECTION", False)
                dpg.add_checkbox(
                    label="启用准星检测",
                    default_value=crosshair_enabled,
                    callback=create_master_switch_callback("ENABLE_CROSSHAIR_DETECTION", crosshair_deps)
                )

                dpg.add_separator()
                dpg.add_text("检测器配置", color=UIColors.SECTION_HEADER)

                add_combo_tagged(
                    "CROSSHAIR_DETECTOR_TYPE",
                    "检测器类型",
                    ["color", "template", "cross_shape"],
                    "crosshair_detector_type"
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
                dpg.add_text("外部模板配置", color=UIColors.SECTION_HEADER)

                add_input_text_tagged(
                    "CROSSHAIR_TEMPLATE_PATH",
                    "模板图片路径",
                    "crosshair_template_path"
                )

                dpg.add_text("说明: 用于 template 模式，支持相对/绝对路径",
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

                update_dependent_controls("ENABLE_CROSSHAIR_DETECTION", crosshair_deps, crosshair_enabled)

            # ================= TAB 4: 预览窗口 =================
            with dpg.tab(label="预览窗口"):
                dpg.add_text("窗口基础设置", color=UIColors.APPLE_BLUE)

                preview_deps = [
                    "preview_width", "preview_height", "preview_skip",
                    "preview_show_boxes", "preview_show_labels", "preview_show_conf",
                    "preview_show_fps", "preview_show_cross", "preview_show_aim",
                    "preview_box_thick", "preview_text_scale"
                ]
                preview_enabled = cfg.get_config("ENABLE_PREVIEW_WINDOW", False)
                dpg.add_checkbox(
                    label="启用预览窗口",
                    default_value=preview_enabled,
                    callback=create_master_switch_callback("ENABLE_PREVIEW_WINDOW", preview_deps)
                )

                add_int_tagged("PREVIEW_WINDOW_WIDTH", "窗口宽度", 400, 1920, "preview_width")
                add_int_tagged("PREVIEW_WINDOW_HEIGHT", "窗口高度", 400, 1080, "preview_height")
                add_int_tagged("PREVIEW_FRAME_SKIP", "跳帧数 (0=不跳帧)", 0, 10, "preview_skip")

                dpg.add_separator()
                dpg.add_text("显示选项", color=UIColors.SECTION_HEADER)
                add_bool_tagged("PREVIEW_SHOW_BOXES", "显示检测框", "preview_show_boxes")
                add_bool_tagged("PREVIEW_SHOW_LABELS", "显示类别标签", "preview_show_labels")
                add_bool_tagged("PREVIEW_SHOW_CONFIDENCE", "显示置信度", "preview_show_conf")
                add_bool_tagged("PREVIEW_SHOW_FPS", "显示 FPS 信息", "preview_show_fps")
                add_bool_tagged("PREVIEW_SHOW_CROSSHAIR", "显示准心十字线", "preview_show_cross")
                add_bool_tagged("PREVIEW_SHOW_AIM_POINT", "显示瞄准点", "preview_show_aim")

                dpg.add_separator()
                dpg.add_text("视觉样式", color=UIColors.SECTION_HEADER)
                add_int_tagged("PREVIEW_BOX_THICKNESS", "检测框线宽", 1, 5, "preview_box_thick")
                add_float_tagged("PREVIEW_TEXT_SCALE", "文字大小缩放", 0.3, 1.5, "preview_text_scale")

                update_dependent_controls("ENABLE_PREVIEW_WINDOW", preview_deps, preview_enabled)

            # ================= TAB 5: 视觉识别 =================
            with dpg.tab(label="视觉识别"):
                dpg.add_text("检测参数", color=UIColors.APPLE_BLUE)
                add_float("CONF_THRESHOLD", "置信度阈值", 0.1, 0.99)
                add_float("IOU_THRESHOLD", "重叠剔除 (IOU)", 0.1, 0.99)

                dpg.add_separator()
                dpg.add_text("目标 ID 选择", color=UIColors.APPLE_BLUE)

                current_ids = cfg.get_config("TARGET_CLASS_IDS", [])
                for i in range(10):
                    if i % 5 == 0:
                        group_tag = dpg.add_group(horizontal=True)
                    is_active = i in current_ids
                    dpg.add_checkbox(
                        label=f"ID {i}",
                        default_value=is_active,
                        callback=update_class_ids_callback,
                        user_data=i,
                        parent=group_tag
                    )
                    dpg.add_spacer(width=20, parent=group_tag)

                dpg.add_separator()
                dpg.add_text("头部优先策略", color=UIColors.SECTION_HEADER)

                head_priority_deps = [
                    "head_class_id",
                    "head_priority_range",
                    "ignore_small_head",
                    "small_target_threshold"
                ]
                head_priority_enabled = cfg.get_config("ENABLE_HEAD_PRIORITY", True)
                dpg.add_checkbox(
                    label="启用头部优先",
                    default_value=head_priority_enabled,
                    callback=create_master_switch_callback("ENABLE_HEAD_PRIORITY", head_priority_deps)
                )

                add_int_tagged("HEAD_CLASS_ID", "头部 ID 定义", 0, 10, "head_class_id")
                add_int_tagged("HEAD_PRIORITY_RANGE", "头部优先距离范围 (像素)", 0, 500, "head_priority_range")

                dpg.add_text("说明：在目标组内，头部可以比最近检测框远多少像素",
                             color=UIColors.TEXT_GRAY)

                dpg.add_separator()
                dpg.add_text("小目标头部过滤 (新增)", color=UIColors.SECTION_HEADER)

                small_target_deps = ["small_target_threshold"]
                ignore_small_head_enabled = cfg.get_config("IGNORE_SMALL_TARGET_HEAD", True)
                dpg.add_checkbox(
                    label="忽略小目标的头部检测框",
                    default_value=ignore_small_head_enabled,
                    callback=create_master_switch_callback("IGNORE_SMALL_TARGET_HEAD", small_target_deps),
                    tag="ignore_small_head"
                )

                add_int_tagged("SMALL_TARGET_AREA_THRESHOLD", "小目标尺寸阈值 (像素)", 10, 1000,
                               "small_target_threshold")

                dpg.add_text("说明：当检测框宽度或高度 < 此值时，忽略头部类别",
                             color=UIColors.TEXT_GRAY)
                dpg.add_text("适用场景：远距离目标 / 头部抖动严重时",
                             color=UIColors.TEXT_GRAY)

                update_dependent_controls("ENABLE_HEAD_PRIORITY", head_priority_deps, head_priority_enabled)
                update_dependent_controls("IGNORE_SMALL_TARGET_HEAD", small_target_deps, ignore_small_head_enabled)

            # ================= TAB 6: PID 瞄准 =================
            with dpg.tab(label="PID 控制"):
                dpg.add_text("瞄准偏移", color=UIColors.APPLE_BLUE)
                add_float("AIM_Y_RATIO", "Y轴 瞄准高度 (0.5=中心)", 0.0, 1.0)
                add_float("AIM_X_OFFSET", "X轴 微调偏移", -100.0, 100.0)

                dpg.add_separator()
                dpg.add_text("PID 参数 (X 横向)", color=UIColors.SECTION_HEADER)
                add_float("PID_KP_X", "P (比例-速度)", 0.0, 5.0, speed=0.01)
                add_float("PID_KI_X", "I (积分-误差)", 0.0, 2.0, speed=0.001)
                add_float("PID_KD_X", "D (微分-阻尼)", 0.0, 1.0, speed=0.001)

                dpg.add_separator()
                dpg.add_text("PID 参数 (Y 纵向)", color=UIColors.SECTION_HEADER)
                add_float("PID_KP_Y", "P (比例-速度)", 0.0, 5.0, speed=0.01)
                add_float("PID_KI_Y", "I (积分-误差)", 0.0, 2.0, speed=0.001)
                add_float("PID_KD_Y", "D (微分-阻尼)", 0.0, 1.0, speed=0.001)

                dpg.add_separator()
                dpg.add_text("限制与死区", color=UIColors.SECTION_HEADER)
                add_int("MAX_SINGLE_MOVE_PX", "单帧最大移动像素", 1, 2000)
                add_int("PRECISION_DEAD_ZONE", "瞄准死区 (像素)", 0, 50)
                add_int("DEFAULT_DELAY_MS_PER_STEP", "每步延迟 (ms)", 0, 50)

            # ================= TAB 7: 目标追踪 =================
            with dpg.tab(label="目标追踪"):
                dpg.add_text("目标分组设置", color=UIColors.APPLE_BLUE)
                add_int("TARGET_GROUP_DISTANCE_THRESHOLD", "身体头部分组距离阈值", 10, 500)
                add_int("TARGET_ID_GRID_SIZE", "目标ID网格大小 (像素)", 5, 100)

                dpg.add_text("说明：身体和头部距离小于此值时认为是同一个目标",
                             color=UIColors.TEXT_GRAY)

                dpg.add_separator()
                dpg.add_text("目标选择与锁定", color=UIColors.SECTION_HEADER)
                add_int("MIN_TARGET_LOCK_FRAMES", "最小锁定帧数", 1, 100)
                add_int("TARGET_SWITCH_DISTANCE_THRESHOLD", "切换距离阈值 (像素)", 10, 500)
                add_int("TARGET_IDENTITY_DISTANCE", "同目标判定距离 (像素)", 10, 500)
                add_int("MAX_LOST_FRAMES", "丢失目标容忍帧", 1, 300)

                dpg.add_separator()
                dpg.add_text("卡尔曼滤波 (Kalman)", color=UIColors.SECTION_HEADER)

                kalman_deps = ["kalman_process", "kalman_measure", "kalman_predict"]
                kalman_enabled = cfg.get_config("USE_KALMAN_FILTER", True)
                dpg.add_checkbox(
                    label="启用卡尔曼滤波",
                    default_value=kalman_enabled,
                    callback=create_master_switch_callback("USE_KALMAN_FILTER", kalman_deps)
                )

                add_float_tagged("KALMAN_PROCESS_NOISE", "过程噪声", 0.01, 10.0, "kalman_process")
                add_float_tagged("KALMAN_MEASUREMENT_NOISE", "测量噪声", 0.1, 50.0, "kalman_measure")
                add_int_tagged("KALMAN_MAX_PREDICT_FRAMES", "最大预测帧数", 0, 60, "kalman_predict")

                update_dependent_controls("USE_KALMAN_FILTER", kalman_deps, kalman_enabled)

                dpg.add_separator()
                dpg.add_text("EMA 平滑 (备用)", color=UIColors.SECTION_HEADER)
                add_float("AIM_POINT_SMOOTH_ALPHA", "瞄准点平滑系数 (仅在禁用卡尔曼时生效)", 0.01, 1.0)

                dpg.add_separator()
                dpg.add_text("移动预判", color=UIColors.SECTION_HEADER)

                lead_deps = ["lead_frames"]
                lead_enabled = cfg.get_config("ENABLE_LEAD_TARGET", False)
                dpg.add_checkbox(
                    label="启用移动预判",
                    default_value=lead_enabled,
                    callback=create_master_switch_callback("ENABLE_LEAD_TARGET", lead_deps)
                )

                add_int_tagged("LEAD_FRAMES", "预判提前量 (帧)", 0, 30, "lead_frames")
                update_dependent_controls("ENABLE_LEAD_TARGET", lead_deps, lead_enabled)

            # ================= TAB 8: 压枪系统 =================
            with dpg.tab(label="压枪配置"):
                dpg.add_text("总开关", color=UIColors.APPLE_BLUE)

                recoil_deps = [
                    "recoil_ctrl", "recoil_mode", "recoil_req_target", "recoil_req_lock",
                    "recoil_timeout", "recoil_lock_frames", "recoil_pattern", "recoil_v_speed",
                    "recoil_h_speed", "recoil_inc_y", "recoil_h_var", "recoil_max_move",
                    "recoil_max_x", "recoil_max_y"
                ]
                recoil_enabled = cfg.get_config("ENABLE_MANUAL_RECOIL", True)
                dpg.add_checkbox(
                    label="启用压枪系统",
                    default_value=recoil_enabled,
                    callback=create_master_switch_callback("ENABLE_MANUAL_RECOIL", recoil_deps)
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

                update_dependent_controls("ENABLE_MANUAL_RECOIL", recoil_deps, recoil_enabled)

            # ================= TAB 9: 自动开火 =================
            with dpg.tab(label="自动开火"):

                autofire_deps = ["autofire_debug", "autofire_acc", "autofire_dist", "autofire_lock"]
                autofire_enabled = cfg.get_config("ENABLE_AUTO_FIRE", False)
                dpg.add_checkbox(
                    label="🔥 启用自动开火",
                    default_value=autofire_enabled,
                    callback=create_master_switch_callback("ENABLE_AUTO_FIRE", autofire_deps)
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

                update_dependent_controls("ENABLE_AUTO_FIRE", autofire_deps, autofire_enabled)

            # ================= TAB 10: 驱动与按键 =================
            with dpg.tab(label="驱动 & 按键"):
                dpg.add_text("硬件模式选择", color=UIColors.APPLE_BLUE)
                dpg.add_text("Makcu 和 传统驱动 只能选一个", color=UIColors.ERROR_RED)

                dpg.add_separator()
                dpg.add_text("Makcu 硬件模式", color=UIColors.SECTION_HEADER)

                makcu_deps = ["makcu_port", "makcu_reconnect"]
                makcu_enabled = cfg.get_config("USE_MAKCU", False)
                dpg.add_checkbox(
                    label="启用 Makcu 硬件",
                    default_value=makcu_enabled,
                    callback=create_master_switch_callback("USE_MAKCU", makcu_deps)
                )

                add_input_text_tagged("MAKCU_PORT", "Makcu COM口 (留空自动搜索)", "makcu_port")
                add_bool_tagged("MAKCU_AUTO_RECONNECT", "Makcu 断线自动重连", "makcu_reconnect")
                update_dependent_controls("USE_MAKCU", makcu_deps, makcu_enabled)

                dpg.add_separator()
                dpg.add_text("🖱 驱动模式", color=UIColors.TEXT_GRAY)

                driver_deps = ["driver_fallback", "driver_path", "driver_request", "driver_mickey"]
                driver_enabled = cfg.get_config("USE_DRIVER_MODE", False)
                dpg.add_checkbox(
                    label="使用传统硬件驱动 (与Makcu互斥)",
                    default_value=driver_enabled,
                    callback=create_master_switch_callback("USE_DRIVER_MODE", driver_deps)
                )

                add_bool_tagged("MOUSE_MODE_AUTO_FALLBACK", "驱动失败自动回退", "driver_fallback")
                add_input_text_tagged("DRIVER_PATH", "驱动设备路径", "driver_path")
                add_int_tagged("MOUSE_REQUEST", "鼠标 Request Code", 0, 9999999, "driver_request")
                add_int_tagged("MAX_MICKEY", "鼠标移动量限制 (Mickey)", 100, 5000, "driver_mickey")
                update_dependent_controls("USE_DRIVER_MODE", driver_deps, driver_enabled)

                dpg.add_separator()
                dpg.add_text("按键监控配置", color=UIColors.TEXT_GRAY)
                dpg.add_text("  选择哪些按键触发瞄准", color=UIColors.TEXT_GRAY, indent=20)

                add_bool("ENABLE_LEFT_MOUSE_MONITOR", "监控左键")
                add_bool("ENABLE_RIGHT_MOUSE_MONITOR", "监控右键")
                add_bool("ENABLE_MOUSE4_MONITOR", "监控侧键4 (后退键)")
                add_bool("ENABLE_MOUSE5_MONITOR", "监控侧键5 (前进键)")

                dpg.add_separator()
                add_int("KEY_MONITOR_INTERVAL_MS", "监控间隔 (ms)", 10, 1000)

                dpg.add_separator()
                dpg.add_text("⚙ 按键映射 ID (高级选项，谨慎修改)", color=UIColors.TEXT_GRAY)
                add_int("APP_MOUSE_LEFT_DOWN", "Left Down ID", 0, 100)
                add_int("APP_MOUSE_LEFT_UP", "Left Up ID", 0, 100)
                add_int("APP_MOUSE_RIGHT_DOWN", "Right Down ID", 0, 100)
                add_int("APP_MOUSE_RIGHT_UP", "Right Up ID", 0, 100)

            # ================= TAB 11: 脚本扩展 =================
            with dpg.tab(label="脚本扩展"):
                dpg.add_text("脚本执行设置", color=UIColors.APPLE_BLUE)
                add_bool("SCRIPT_AUTO_RELOAD", "脚本自动重载 (监听文件修改)")
                add_bool("SCRIPT_DEBUG_MODE", "脚本调试模式 (输出详细日志)")
                add_int("SCRIPT_TIMEOUT_MS", "脚本执行超时 (ms)", 1, 1000)

                dpg.add_separator()

                with dpg.group(horizontal=True):
                    dpg.add_text("可用脚本列表", color=UIColors.SECTION_HEADER)
                    dpg.add_button(label="刷新列表", callback=refresh_scripts_ui, small=True)

                dpg.add_text("勾选以启用脚本 (自动保存至配置)", color=UIColors.TEXT_GRAY)

                # === 脚本列表容器 ===
                dpg.add_group(tag="script_list_container")

    dpg.create_viewport(title='AI Config Ultimate v6.0 - Apple UI', width=900, height=820)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("Primary Window", True)

    refresh_scripts_ui()

    global _gui_running
    _gui_running = True

    try:
        while dpg.is_dearpygui_running():
            if _gui_exit_event.is_set():
                print("[GUI] 收到退出信号，准备关闭...")
                dpg.stop_dearpygui()
                break
            dpg.render_dearpygui_frame()

    finally:
        dpg.destroy_context()
        _gui_running = False
        print("[GUI] ✅ GUI 已完全清理")


# ================= 通用控件封装（无tag版本） =================

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


# ================= 通用控件封装（带tag版本 - 用于联动） =================

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


# ================= 外部控制函数 =================

def stop_gui():
    print("[GUI] 正在请求 GUI 退出...")
    _gui_exit_event.set()


def is_gui_running():
    return _gui_running


if __name__ == "__main__":
    create_gui()
