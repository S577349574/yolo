import sys
import threading
import dearpygui.dearpygui as dpg
import config_manager as cfg
import os
import glob
import cv2
import numpy as np

import utils

# 1. 加载配置
cfg.load_config()

# ========== 全局退出信号 ==========
_gui_exit_event = threading.Event()
_gui_running = False

# 脚本文件夹路径



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
# ================= 核心控制回调 =================

def update_ai_button_status(is_running):
    """根据运行状态更新按钮颜色和文字"""
    if is_running:
        dpg.configure_item("ai_toggle_btn", label="系统运行中 (点击暂停)")
        dpg.bind_item_theme("ai_toggle_btn", "theme_btn_running")
    else:
        dpg.configure_item("ai_toggle_btn", label="系统已暂停 (点击启动)")
        dpg.bind_item_theme("ai_toggle_btn", "theme_btn_paused")


def toggle_ai_callback(sender, app_data, user_data):
    """启动/暂停 AI"""
    resume_event, _, _ = cfg.get_events()

    if resume_event.is_set():
        # 正在运行 -> 执行暂停
        resume_event.clear()
        update_ai_button_status(False)
        # 可选：同步写入配置，下次启动记住状态
        # cfg.set_config("AI_ENABLED", False)
        print("[GUI] 发送暂停信号")
    else:
        # 暂停中 -> 执行启动
        resume_event.set()
        update_ai_button_status(True)
        # cfg.set_config("AI_ENABLED", True)
        print("[GUI] 发送启动信号")


def manual_reload_callback(sender, app_data, user_data):
    """强制热重载资源"""
    resume_event, reload_event, _ = cfg.get_events()

    print("[GUI] 发送强制重载信号...")
    reload_event.set()

    # 如果当前是暂停状态，必须临时唤醒主线程让它去处理重载
    if not resume_event.is_set():
        resume_event.set()
        # 重载后是否保持暂停，取决于你的业务逻辑，这里默认重载后会让它运行
        update_ai_button_status(True)


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

    if key in ["AIM_X_OFFSET", "AIM_Y_RATIO"]:
        update_aim_offset_preview()


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
    """
    sender: checkbox 的 ID
    app_data: 当前 checkbox 的值 (True/False)
    user_data: 脚本名称 (例如 "debug_system")
    """
    script_name = user_data
    is_enabled = app_data

    # 1. 获取当前已启用的脚本列表
    current_enabled = cfg.get_config("ENABLED_SCRIPTS", [])

    # 如果读取到的是字符串（为了兼容老配置），先转为列表
    if isinstance(current_enabled, str):
        current_enabled = [s.strip() for s in current_enabled.split(',') if s.strip()]

    # 2. 根据勾选状态更新列表
    if is_enabled:
        if script_name not in current_enabled:
            current_enabled.append(script_name)
    else:
        if script_name in current_enabled:
            current_enabled.remove(script_name)

    # 3. 写回配置文件
    # 建议保存为列表格式，这样 Python 处理起来最方便
    cfg.set_config("ENABLED_SCRIPTS", current_enabled)

    # 4. 刷新 UI 显示（可选，用于更新旁边的 "(已启用)" 文字）
    refresh_scripts_ui()


def refresh_scripts_ui():
    SCRIPTS_DIR = utils.get_scripts_dir()
    """扫描文件夹并重建脚本列表 UI"""
    # 打印出当前 UI 正在尝试搜索的具体路径
    print(f"[UI Debug] 正在扫描脚本目录: {SCRIPTS_DIR}")
    """扫描文件夹并重建脚本列表 UI"""
    dpg.delete_item("script_list_container", children_only=True)

    if not os.path.exists(SCRIPTS_DIR):
        os.makedirs(SCRIPTS_DIR)

    lua_files = glob.glob(os.path.join(SCRIPTS_DIR, "*.lua"))
    script_names = [os.path.splitext(os.path.basename(f))[0] for f in lua_files]
    enabled_config = cfg.get_config("ENABLED_SCRIPTS", [])
    # 统一转换为列表，确保 name in enabled_scripts 判断准确
    if isinstance(enabled_config, str):
        enabled_scripts = [s.strip() for s in enabled_config.split(',') if s.strip()]
    else:
        enabled_scripts = enabled_config

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
    """配置中文字体支持"""
    with dpg.font_registry():
        # 尝试多个字体路径
        font_paths = [
            r"C:\Windows\Fonts\msyh.ttc",  # 微软雅黑
            r"C:\Windows\Fonts\simhei.ttf",  # 黑体
            r"C:\Windows\Fonts\simsun.ttc",  # 宋体
        ]

        font_path = None
        for path in font_paths:
            if os.path.exists(path):
                font_path = path
                break

        if font_path:
            # ✅ 修复：使用 add_font() 而不是 with dpg.font()
            with dpg.font(font_path, 18) as font_cn:
                # ✅ 添加字符范围提示（关键修复）
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Simplified_Common)
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Full)

                # 手动添加常用字符范围
                dpg.add_font_range(0x0020, 0x00FF)  # 基本拉丁字母
                dpg.add_font_range(0x4E00, 0x9FFF)  # 中日韩统一表意文字（扩大范围）
                dpg.add_font_range(0x3000, 0x303F)  # 中日韩符号和标点

            dpg.bind_font(font_cn)
            print(f"[GUI] 已加载中文字体: {font_path}")
        else:
            print("[GUI] 未找到中文字体，部分中文可能显示为问号")


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
    with dpg.item_handler_registry(tag="preview_handler"):
        # 激活状态（拖动中）
        dpg.add_item_active_handler(callback=_handle_preview_drag)
        # 点击状态（点击即定位）
        dpg.add_item_clicked_handler(callback=_handle_preview_drag)

    # 绿色主题 (运行中)
    with dpg.theme(tag="theme_btn_running"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (46, 125, 50))       # 深绿
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (56, 142, 60))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (27, 94, 32))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255))

    # 红色主题 (已暂停)
    with dpg.theme(tag="theme_btn_paused"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (198, 40, 40))      # 深红
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (211, 47, 47))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (183, 28, 28))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255))
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



    with dpg.window(tag="Primary Window", label="test-v1.0"):

        # === 顶部状态栏 ===
        with dpg.group(horizontal=True):
            # dpg.add_text("--", color=UIColors.APPLE_BLUE)
            dpg.add_button(
                tag="ai_toggle_btn",
                label="初始化中...",
                callback=toggle_ai_callback,
                width=160,
                height=30
            )
            # [核心功能] 强制重载 按钮
            dpg.add_button(
                label="重载配置/模型",
                callback=manual_reload_callback,
                height=30
            )
            # 保存按钮
            dpg.add_button(label="保存所有配置 (Save)", callback=save_callback, height=30, width=160)
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("修改参数后必须点击此处才可以生效,\n如果不点击保存直接点击重启参数修改会丢失.")
            dpg.add_text("[就绪]", tag="status_text", color=UIColors.TEXT_GRAY)

        dpg.add_separator()

        with dpg.tab_bar():

            # ================= TAB 1: 基础设置 =================
            with dpg.tab(label="基础 & 系统"):
                # ========== 原有配置（保持不变） ==========
                dpg.add_text("许可证配置", color=UIColors.APPLE_BLUE)
                add_input_text("LICENSE_KEY", "许可证密钥 (License)")
                # ========== 🔥 新增：核心模型配置 ========== ⭐
                dpg.add_text("核心模型配置", color=UIColors.APPLE_BLUE)

                add_input_text("MODEL_PATH", "YOLO 模型路径 (.onnx)")
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "此目录是绝对路径，你模型存放的文件在哪里，就直接复制路径填入输入框，模型名字要包含.onnx\n"
                        "比如我模型放的目录是在，C盘模型文件夹下面叫320.onnx的话\n"
                        "那路径就是C:\\模型\\320.onnx"
                    )
                add_combo(
                    "MODEL_TYPE",
                    "YOLO 模型类型",
                    ["v5", "v8", "v10", "v11"]
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("根据不同模型训练方式选择不同的类型，一般模型名字上都会标注出是v5或者v8\n"
                        "比如我有一个模型名叫：0923lqm320v5s.onnx\n"
                        "0923是训练日期、lqm是作者的名字、320是模型的尺寸、v5s就是模型的类型\n"
                        "如果要使用这个模型，那么此处就要选择V5\n"
                        "如果你无法判断模型是V几的，优先选择v8，打开预览窗口后如果发现花屏，在尝试V5\n"
                    )

                add_combo(
                    "FORCE_BACKEND",
                    "推理后端 (留空自动)",
                    ["tensorrt", "cuda", "dml", "ncnn_vulkan", "ncnn_cpu", "cpu"]
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "tensorrt = TensorRT (仅NVIDIA)\n"
                        "cuda = CUDA (NVIDIA)\n"
                        "dml = DirectML (AMD/Intel)\n"
                        "ncnn_vulkan = ncnn Vulkan (AMD推荐)\n"
                        "ncnn_cpu = ncnn CPU模式\n"
                        "cpu = 纯CPU模式"
                    )


                dpg.add_separator()

                # ========== 🔥 新增：推理引擎高级配置（可折叠） ========== ⭐
                with dpg.collapsing_header(label="推理引擎高级配置", default_open=False):
                    dpg.add_text("ONNX Runtime 配置", color=UIColors.SECTION_HEADER)
                    add_bool("USE_TENSORRT", "启用 TensorRT 加速 (仅NVIDIA)")
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("需要安装 TensorRT 并配置环境变量")

                    dpg.add_separator()
                    dpg.add_text("ncnn 模型文件配置", color=UIColors.SECTION_HEADER)
                    dpg.add_text("说明：留空则自动从 MODEL_PATH 推断", color=UIColors.TEXT_GRAY, indent=20)

                    add_input_text("NCNN_PARAM_PATH", "ncnn 参数文件 (.param)")
                    add_input_text("NCNN_BIN_PATH", "ncnn 权重文件 (.bin)")

                    dpg.add_separator()
                    dpg.add_text("ncnn 网络结构配置", color=UIColors.SECTION_HEADER)
                    dpg.add_text("说明：留空则自动从 .param 文件检测", color=UIColors.TEXT_GRAY, indent=20)

                    add_input_text("NCNN_INPUT_NAME", "输入层名称")
                    # NCNN_OUTPUT_NAMES 是列表，需要特殊处理
                    current_outputs = cfg.get_config("NCNN_OUTPUT_NAMES", None)
                    output_str = "" if current_outputs is None else ",".join(current_outputs)
                    dpg.add_input_text(
                        label="输出层名称（逗号分隔）",
                        default_value=output_str,
                        callback=lambda s, a: cfg.set_config(
                            "NCNN_OUTPUT_NAMES",
                            [x.strip() for x in a.split(",") if x.strip()] if a.strip() else None
                        ),
                        width=280
                    )
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("示例: out0,out1,out2\n留空自动检测")

                    dpg.add_separator()
                    dpg.add_text("ncnn 性能优化", color=UIColors.SECTION_HEADER)
                    add_bool("NCNN_USE_FP16", "启用 FP16 加速 (仅GPU)")
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("半精度浮点运算，提升 AMD GPU 性能")

                    dpg.add_separator()
                    dpg.add_text("类别名称配置", color=UIColors.SECTION_HEADER)
                    add_input_text("CLASS_NAMES_PATH", "类别名称文件路径")
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("示例: models/names.txt\n留空则从模型目录自动加载 names.txt")

                dpg.add_separator()
                dpg.add_text("系统性能", color=UIColors.APPLE_BLUE)
                add_bool("ENABLE_LOGGING", "启用日志记录")
                add_combo("LOG_LEVEL", "日志等级", ["DEBUG", "INFO", "WARNING", "ERROR"])
                add_bool("DEBUG_MODE", "调试模式 (显示画框)")
                add_bool("MAKCU_DEBUG_MODE", "Makcu调试模式")

                add_int("CAPTURE_FPS", "截图帧率限制", 1, 500)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("截图帧数限制，这个设置要超过你屏幕刷新率\n"
                        "在右键显示设置-高级显示设置中可以看到屏幕刷新率\n"
                    )
                add_int("INFERENCE_FPS", "推理帧率限制", 1, 500)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("推理帧数可以设置的很高，因为在游戏环境中，GPU会优先把资源给游戏，程序的AI推理只能吃剩下的\n"
                        "如果你发现推理很低，那么你就需要限制一下游戏的fps或者画质，让程序推理有资源可吃\n"
                        "如果想要实现精准的锁抢，那么你推理的速度一定要比你游戏fps速度高。比如游戏120fps的，推理就需要130fps\n"
                    )
                add_int("CONFIG_MONITOR_INTERVAL_SEC", "配置热重载间隔 (秒)", 1, 60)

            # ================= TAB 2: 图像源配置 =================
            with dpg.tab(label="图像源"):
                dpg.add_text("画面来源模式(需要重启启动)", color=UIColors.APPLE_BLUE)
                add_combo("IMAGE_SOURCE_TYPE", "图像源类型", ["local", "network"])
                add_int("CROP_SIZE", "推理区域大小 (Crop)", 64, 1280)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("在v1.2版本以后，此参数可以忽略，程序将优先从onnx模型文件中提取需要的截图尺寸。\n"
                                 "此参数在v1.2以后为兜底参数可以不调整\n"
                    )
                dpg.add_separator()
                dpg.add_text("网络画面接收配置(需要重启启动) (仅network模式生效)", color=UIColors.SECTION_HEADER)
                add_int("FRAME_PORT", "接收端口", 1024, 65535)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("填写游戏机agent配置中的FRAME_PORT参数\n"
                                 "图片来源选择网络，游戏机和推理机必须在一个局域网环境下才可以\n"
                    )
                add_int("FRAME_WIDTH", "画面宽度 (像素)", 64, 1920)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("填写游戏机agent配置中的width参数\n"
                                 "此参数要和onnx模型尺寸同步\n"
                    )
                add_int("FRAME_HEIGHT", "画面高度 (像素)", 64, 1080)
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("填写游戏机agent配置中的height参数\n"
                                 "此参数要和onnx模型尺寸同步\n"
                    )
                add_int("FRAME_CHANNELS", "通道数 (RGB=3, RGBA=4)", 3, 4)



            # ================= TAB 3: 预览窗口 =================
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
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("尺寸可以不和onnx模型一样，可以自定义大小\n"
                    )

                add_int_tagged("PREVIEW_WINDOW_HEIGHT", "窗口高度", 400, 1080, "preview_height")
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("尺寸可以不和onnx模型一样，可以自定义大小\n"
                    )
                add_int_tagged("PREVIEW_FRAME_SKIP", "跳帧数 (0=不跳帧)", 0, 10, "preview_skip")
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("设置0就是在预览窗口显示所有的截图，设置1就是2张截图只显示1张。\n"
                        "比如，你的fps是120，如果设置1，预览窗口就变成60fps\n"
                        "此预览窗口是异步画面，不影响程序性能，也不会造成真是推理帧数降低。\n"
                    )

                dpg.add_separator()
                dpg.add_text("显示选项", color=UIColors.SECTION_HEADER)
                add_bool_tagged("PREVIEW_SHOW_BOXES", "显示检测框", "preview_show_boxes")
                add_bool_tagged("PREVIEW_SHOW_LABELS", "显示类别标签", "preview_show_labels")
                add_bool_tagged("PREVIEW_SHOW_CONFIDENCE", "显示置信度", "preview_show_conf")
                add_bool_tagged("PREVIEW_SHOW_FPS", "显示 FPS 信息", "preview_show_fps")
                add_bool_tagged("PREVIEW_SHOW_CROSSHAIR", "显示准心十字线", "preview_show_cross")
                add_bool_tagged("PREVIEW_SHOW_AIM_POINT", "显示瞄准点", "preview_show_aim")
                add_bool_tagged("PREVIEW_SHOW_SEARCH_AREA", "显示准星搜索区域", "preview_show_search")

                dpg.add_separator()
                dpg.add_text("视觉样式", color=UIColors.SECTION_HEADER)
                add_int_tagged("PREVIEW_BOX_THICKNESS", "检测框线宽", 1, 5, "preview_box_thick")
            # ================= TAB 10: 驱动与按键 =================
            with dpg.tab(label="驱动 & 按键"):
                dpg.add_text("硬件模式选择", color=UIColors.APPLE_BLUE)
                dpg.add_text(r"Makcu\MTKmbox\传统驱动只能选一个", color=UIColors.ERROR_RED)

                # ========== Makcu 硬件模式 ==========
                dpg.add_separator()
                dpg.add_text("Makcu 硬件模式", color=UIColors.SECTION_HEADER)

                makcu_deps = ["makcu_port", "makcu_reconnect", "makcu_interval", "makcu_queue",
                              "makcu_hw_monitor", "makcu_fallback"]
                makcu_enabled = cfg.get_config("USE_MAKCU", False)
                dpg.add_checkbox(
                    label="启用 Makcu 硬件",
                    default_value=makcu_enabled,
                    callback=create_master_switch_callback("USE_MAKCU", makcu_deps)
                )

                add_input_text_tagged("MAKCU_PORT", "Makcu COM口 (留空自动搜索)", "makcu_port")
                add_bool_tagged("MAKCU_AUTO_RECONNECT", "Makcu 断线自动重连", "makcu_reconnect")

                add_float_input_tagged("MAKCU_MIN_SEND_INTERVAL", "发送间隔 (秒)", "makcu_interval")
                with dpg.tooltip("makcu_interval"):
                    dpg.add_text("串口写入的最小时间间隔\n如果出现 Write Timeout 或卡顿，请调大此值")

                add_int_input_tagged("MAKCU_QUEUE_SIZE", "指令队列缓冲", "makcu_queue")

                add_bool_tagged("MAKCU_USE_HARDWARE_MONITOR", "使用硬件按键监控", "makcu_hw_monitor")
                add_bool_tagged("MAKCU_FALLBACK_TO_PYNPUT", "监控失败时回退到软件", "makcu_fallback")

                update_dependent_controls("USE_MAKCU", makcu_deps, makcu_enabled)

                # ========== MTKmbox 硬件模式 ==========
                dpg.add_separator()
                dpg.add_text("MTKmbox 硬件模式", color=UIColors.SECTION_HEADER)

                mtk_deps = ["mtk_port", "mtk_vid", "mtk_pid", "mtk_max_move",
                            "mtk_hw_monitor", "mtk_fallback", "mtk_debug"]
                mtk_enabled = cfg.get_config("USE_MTKMBOX", False)
                dpg.add_checkbox(
                    label="启用 MTKmbox 硬件 (与Makcu/驱动互斥)",
                    default_value=mtk_enabled,
                    callback=create_master_switch_callback("USE_MTKMBOX", mtk_deps)
                )

                add_input_text_tagged("MTKMBOX_PORT", "MTKmbox COM口", "mtk_port")

                add_int_input_tagged("MTKMBOX_VID", "USB VID (十进制)", "mtk_vid")
                with dpg.tooltip("mtk_vid"):
                    dpg.add_text("设备 Vendor ID，默认 1046 (0x0416)")

                add_int_input_tagged("MTKMBOX_PID", "USB PID (十进制)", "mtk_pid")
                with dpg.tooltip("mtk_pid"):
                    dpg.add_text("设备 Product ID，默认 20512 (0x5020)")

                add_int_input_tagged("MTKMBOX_MAX_MOVE", "单次最大移动量", "mtk_max_move")
                with dpg.tooltip("mtk_max_move"):
                    dpg.add_text("MTKmbox 单次移动的最大像素值\n协议限制：1-127")

                add_bool_tagged("MTKMBOX_USE_HARDWARE_MONITOR", "使用硬件按键监控", "mtk_hw_monitor")
                add_bool_tagged("MTKMBOX_FALLBACK_TO_PYNPUT", "监控失败时回退到软件", "mtk_fallback")
                add_bool_tagged("MTKMBOX_DEBUG_MODE", "MTKmbox 调试模式", "mtk_debug")

                update_dependent_controls("USE_MTKMBOX", mtk_deps, mtk_enabled)

                # ========== 传统驱动模式 ==========
                dpg.add_separator()
                dpg.add_text("传统驱动模式", color=UIColors.SECTION_HEADER)

                driver_deps = ["driver_fallback", "driver_path", "driver_request", "driver_mickey"]
                driver_enabled = cfg.get_config("USE_DRIVER_MODE", False)
                dpg.add_checkbox(
                    label="使用传统硬件驱动 (与Makcu/MTKmbox互斥)",
                    default_value=driver_enabled,
                    callback=create_master_switch_callback("USE_DRIVER_MODE", driver_deps)
                )

                add_bool_tagged("MOUSE_MODE_AUTO_FALLBACK", "驱动失败自动回退", "driver_fallback")
                add_input_text_tagged("DRIVER_PATH", "驱动设备路径", "driver_path")
                add_int_tagged("MOUSE_REQUEST", "鼠标 Request Code", 0, 9999999, "driver_request")
                add_int_tagged("MAX_MICKEY", "鼠标移动量限制 (Mickey)", 100, 5000, "driver_mickey")

                update_dependent_controls("USE_DRIVER_MODE", driver_deps, driver_enabled)

                # ========== 通用串口配置 ==========
                dpg.add_separator()
                dpg.add_text("通用串口配置", color=UIColors.TEXT_GRAY)

                add_float_input_tagged("SERIAL_MIN_SEND_INTERVAL", "串口最小发送间隔 (秒)", "serial_interval")
                with dpg.tooltip("serial_interval"):
                    dpg.add_text("适用于所有串口设备 (Makcu/MTKmbox)\n如果出现通信超时，请调大此值")

                # ========== 按键监控配置 ==========
                dpg.add_separator()
                dpg.add_text("按键监控配置", color=UIColors.APPLE_BLUE)
                dpg.add_text("选择哪些按键触发瞄准", color=UIColors.TEXT_GRAY, indent=20)

                add_bool("ENABLE_LEFT_MOUSE_MONITOR", "监控左键")
                add_bool("ENABLE_RIGHT_MOUSE_MONITOR", "监控右键")
                add_bool("ENABLE_MOUSE4_MONITOR", "监控侧键4 (后退键)")
                add_bool("ENABLE_MOUSE5_MONITOR", "监控侧键5 (前进键)")

                dpg.add_separator()
                add_int("KEY_MONITOR_INTERVAL_MS", "监控间隔 (ms)", 10, 1000)

                # ========== 按键映射 ID ==========
                dpg.add_separator()
                dpg.add_text("按键映射 ID (高级选项，谨慎修改)", color=UIColors.TEXT_GRAY)

                add_int("APP_MOUSE_LEFT_DOWN", "Left Down ID", 0, 100)
                add_int("APP_MOUSE_LEFT_UP", "Left Up ID", 0, 100)
                add_int("APP_MOUSE_RIGHT_DOWN", "Right Down ID", 0, 100)
                add_int("APP_MOUSE_RIGHT_UP", "Right Up ID", 0, 100)

            # ================= TAB 11: 脚本扩展 =================
            with dpg.tab(label="脚本扩展"):
                dpg.add_text("脚本执行设置", color=UIColors.APPLE_BLUE)
                add_bool("ENABLE_SCRIPT_SYSTEM", "是否开启脚本功能")
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
            # ================= TAB 4: 准星检测 =================
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

                    # ⭐ 新增：搜索区域相关控件
                    "crosshair_search_x_left",
                    "crosshair_search_x_right",
                    "crosshair_search_y_up",
                    "crosshair_search_y_down",
                    "crosshair_smooth_factor",
                    "crosshair_max_lost_frames"
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
                    ["color", "template", "cross_shape","red_dot"],
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
                # ⭐⭐⭐ 新增：搜索区域配置 ⭐⭐⭐
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

                # ⭐⭐⭐ 新增：平滑与容错配置 ⭐⭐⭐
                dpg.add_separator()
                dpg.add_text("平滑与容错配置", color=UIColors.SECTION_HEADER)

                add_float_input_tagged(
                    "CROSSHAIR_SMOOTH_FACTOR",
                    "位置平滑系数 (0=无平滑, 1=最大平滑)",
                    "crosshair_smooth_factor",
                    format="%.2f"
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("值越大，准星位置变化越平滑\n建议: 0.2 - 0.5\n设为 0 可禁用平滑")

                add_int_input_tagged(
                    "CROSSHAIR_MAX_LOST_FRAMES",
                    "最大丢失帧数（容错）",
                    "crosshair_max_lost_frames"
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("连续检测失败多少帧后才使用屏幕中心\n建议: 3 - 10 帧")

                dpg.add_separator()



                update_dependent_controls("ENABLE_CROSSHAIR_DETECTION", crosshair_deps, crosshair_enabled)


                add_float_tagged("PREVIEW_TEXT_SCALE", "文字大小缩放", 0.3, 1.5, "preview_text_scale")

                update_dependent_controls("ENABLE_PREVIEW_WINDOW", preview_deps, preview_enabled)

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

                dpg.add_text("说明:在目标组内,头部可以比最近检测框远多少像素",
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

                dpg.add_text("说明:当检测框宽度或高度 < 此值时,忽略头部类别",
                             color=UIColors.TEXT_GRAY)
                dpg.add_text("适用场景:远距离目标 / 头部抖动严重时",
                             color=UIColors.TEXT_GRAY)

                update_dependent_controls("ENABLE_HEAD_PRIORITY", head_priority_deps, head_priority_enabled)
                update_dependent_controls("IGNORE_SMALL_TARGET_HEAD", small_target_deps, ignore_small_head_enabled)

            # ================= TAB 6: PID 瞄准 =================
            with dpg.tab(label="PID 控制"):
                # 上部分：参数设置
                dpg.add_text("瞄准偏移参数", color=UIColors.APPLE_BLUE)
                with dpg.group(horizontal=False):

                    dpg.add_input_float(label="Y轴 瞄准高度", tag="input_aim_y",
                                        default_value=cfg.get_config("AIM_Y_RATIO", 0.5),
                                        min_value=0.0, max_value=1.0, step=0, format="%.3f",
                                        callback=update_config_callback, user_data="AIM_Y_RATIO",width=280)

                    dpg.add_input_float(label="X轴 微调偏移", tag="input_aim_x",
                                        default_value=cfg.get_config("AIM_X_OFFSET", 0.5),
                                        min_value=0.0, max_value=1.0, step=0, format="%.3f",
                                        callback=update_config_callback, user_data="AIM_X_OFFSET",width=280)

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
                add_int("TARGET_ID_GRID_SIZE", "目标ID网格大小 (像素)", 5, 100)

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
                kalman_enabled = cfg.get_config("USE_KALMAN_FILTER", True)
                dpg.add_checkbox(
                    label="启用卡尔曼滤波",
                    default_value=kalman_enabled,
                    callback=create_master_switch_callback("USE_KALMAN_FILTER", kalman_deps)
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

                update_dependent_controls("USE_KALMAN_FILTER", kalman_deps, kalman_enabled)

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
                lead_enabled = cfg.get_config("ENABLE_LEAD_TARGET", False)
                dpg.add_checkbox(
                    label="启用移动预判",
                    default_value=lead_enabled,
                    callback=create_master_switch_callback("ENABLE_LEAD_TARGET", lead_deps)
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
                    label="启用自动开火",
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



    dpg.create_viewport(title="Prism Vision-v1.3", width=900, height=800)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    update_aim_offset_preview()
    dpg.set_primary_window("Primary Window", True)

    refresh_scripts_ui()

    global _gui_running
    _gui_running = True

    resume_event, _, _ = cfg.get_events()
    update_ai_button_status(resume_event.is_set())
    last_running_state = None
    try:
        while dpg.is_dearpygui_running():
            if _gui_exit_event.is_set():
                print("[GUI] 收到退出信号，准备关闭...")
                dpg.stop_dearpygui()
                break
            # ========== 🔥 修复：实时状态同步 ==========
            # 获取当前真实的运行状态
            current_running_state = resume_event.is_set()

            # 如果真实状态和记录的状态不一致（比如被 ConfigManager 自动开启了）
            if current_running_state != last_running_state:
                update_ai_button_status(current_running_state)
                last_running_state = current_running_state
            # =========================================

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

def add_float_input_tagged(key, label, tag=None, format="%.3f"):
    """专门用于数字输入，无加减号，宽度一致"""
    val = float(cfg.get_config(key, 0.0))
    dpg.add_input_float(
        label=label,
        default_value=val,
        tag=tag,
        step=0,              # 隐藏加减号
        format=format,       # 格式化显示
        width=280,           # 统一宽度
        callback=lambda s, a: cfg.set_config(key, a)
    )

def add_int_input_tagged(key, label, tag=None):
    """专门用于整数输入，无加减号，宽度一致"""
    val = int(cfg.get_config(key, 0))
    dpg.add_input_int(
        label=label,
        default_value=val,
        tag=tag,
        step=0,              # 隐藏加减号
        width=280,           # 统一宽度
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


def update_search_bounds(key, value):
    """更新搜索区域配置并实时显示"""
    # 获取当前配置
    bounds = cfg.get_config("CROSSHAIR_SEARCH_BOUNDS", {
        "x_left": -30,
        "x_right": 30,
        "y_up": -150,
        "y_down": 20
    })

    # 更新对应的值
    bounds[key] = value

    # 限制范围（-500 到 500）
    bounds[key] = max(-500, min(500, bounds[key]))

    # 写回配置
    cfg.set_config("CROSSHAIR_SEARCH_BOUNDS", bounds)

    # 更新状态提示
    dpg.configure_item(
        "status_text",
        default_value=f"[未保存] 已修改搜索区域: {key}",
        color=UIColors.WARNING_ORANGE
    )

    # 更新显示的搜索区域大小
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

    # 直接获取鼠标相对于 drawlist 左上角的本地坐标
    # 这能避免 child_window 导致的全局坐标偏移问题
    local_mouse_pos = dpg.get_mouse_pos(local=True)
    rel_x = local_mouse_pos[0]
    rel_y = local_mouse_pos[1]

    # --- 必须与 update_aim_offset_preview 保持严丝合缝的参数 ---
    canvas_w, canvas_h = 100, 160  # Drawlist 尺寸
    rect_w, rect_h = 60, 130       # 人体矩形尺寸
    rect_x_start = (canvas_w - rect_w) // 2
    rect_y_start = 10              # 矩形顶部的起始 Y 偏移
    # ---------------------------------------------------------

    # 计算比例并使用 clamp 限制在 0.0 ~ 1.0 之间
    # 核心公式：(当前本地像素位置 - 矩形起始位置) / 矩形总长度
    new_x_ratio = max(0.0, min(1.0, (rel_x - rect_x_start) / rect_w))
    new_y_ratio = max(0.0, min(1.0, (rel_y - rect_y_start) / rect_h))

    # 更新配置
    cfg.set_config("AIM_X_OFFSET", round(new_x_ratio, 3))
    cfg.set_config("AIM_Y_RATIO", round(new_y_ratio, 3))

    # 同步更新 UI 输入框 (input_float)
    if dpg.does_item_exist("input_aim_x"):
        dpg.set_value("input_aim_x", round(new_x_ratio, 3))
    if dpg.does_item_exist("input_aim_y"):
        dpg.set_value("input_aim_y", round(new_y_ratio, 3))

    # 立即重绘红点位置
    update_aim_offset_preview()

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

    # 1. 绘制背景阴影（增加立体感）
    dpg.draw_rectangle([rect_x + 2, rect_y + 2], [rect_x + rect_w + 2, rect_y + rect_h + 2],
                       color=(0, 0, 0, 20), fill=(0, 0, 0, 20), rounding=5, parent="aim_preview_node")

    # 2. 绘制“人体”轮廓
    dpg.draw_rectangle(
        [rect_x, rect_y], [rect_x + rect_w, rect_y + rect_h],
        color=(180, 180, 180, 255), fill=(255, 255, 255, 255),
        thickness=1, rounding=5, parent="aim_preview_node"
    )

    # 3. 绘制十字参考线（淡淡的）
    center_y = rect_y + rect_h // 2
    center_x = rect_x + rect_w // 2
    dpg.draw_line([rect_x, center_y], [rect_x + rect_w, center_y], color=(230, 230, 230, 255),
                  parent="aim_preview_node")
    dpg.draw_line([center_x, rect_y], [center_x, rect_y + rect_h], color=(230, 230, 230, 255),
                  parent="aim_preview_node")

    # 4. 计算并绘制瞄准点
    dot_x = rect_x + (rect_w * offset_x)
    dot_y = rect_y + (rect_h * offset_y)

    # 呼吸感光圈 (红色半透明背景)
    dpg.draw_circle([dot_x, dot_y], 8, color=(255, 59, 48, 50), fill=(255, 59, 48, 30), parent="aim_preview_node")
    # 核心实点
    dpg.draw_circle([dot_x, dot_y], 4, color=(255, 59, 48, 255), fill=(255, 59, 48, 255), parent="aim_preview_node")

    # 5. 坐标数值显示
    dpg.draw_text([10, 145], f"Target: ({offset_x:.2f}, {offset_y:.2f})", color=UIColors.TEXT_BLACK, size=12,
                  parent="aim_preview_node")
# ================= 外部控制函数 =================

def stop_gui():
    print("[GUI] 正在请求 GUI 退出...")
    _gui_exit_event.set()


def is_gui_running():
    return _gui_running


if __name__ == "__main__":
    create_gui()
