import dearpygui.dearpygui as dpg
import config_manager as cfg
import os
import glob

# 1. 加载配置
cfg.load_config()

# 脚本文件夹路径 (假设在当前目录下)
SCRIPTS_DIR = "scripts"


def save_callback():
    """保存配置"""
    if cfg.save_config():
        dpg.configure_item("status_text", default_value="[成功] 配置已保存至 config.json", color=(0, 255, 0))
    else:
        dpg.configure_item("status_text", default_value="[错误] 保存失败！请检查权限", color=(255, 0, 0))


def update_config_callback(sender, app_data, user_data):
    """通用单值更新回调"""
    key = user_data
    value = app_data
    cfg.set_config(key, value)
    dpg.configure_item("status_text", default_value=f"[未保存] 已修改: {key}", color=(255, 200, 0))


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
    dpg.configure_item("status_text", default_value=f"[未保存] 目标ID更新: {current_ids}", color=(255, 200, 0))


# ================= 脚本管理逻辑 =================

def update_script_state_callback(sender, app_data, user_data):
    """
    处理脚本开关
    user_data: 脚本文件名 (不含 .lua)
    app_data: 是否勾选 (bool)
    """
    script_name = user_data
    is_enabled = app_data

    # 获取当前启用的脚本列表
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
    dpg.configure_item(
        "status_text",
        default_value=f"[未保存] 脚本列表已更新",
        color=(255, 200, 0)
    )

    # ⭐ 关键：立刻重建脚本 UI
    refresh_scripts_ui()


def refresh_scripts_ui():
    """扫描文件夹并重建脚本列表 UI"""
    # 1. 清空现有的列表容器
    dpg.delete_item("script_list_container", children_only=True)

    # 2. 扫描 .lua 文件
    if not os.path.exists(SCRIPTS_DIR):
        os.makedirs(SCRIPTS_DIR)

    # 获取所有 .lua 文件
    lua_files = glob.glob(os.path.join(SCRIPTS_DIR, "*.lua"))
    script_names = [os.path.splitext(os.path.basename(f))[0] for f in lua_files]

    # 获取当前已启用的列表 (用于设置默认勾选状态)
    enabled_scripts = cfg.get_config("ENABLED_SCRIPTS", [])

    if not script_names:
        dpg.add_text("未找到脚本文件 (请在 scripts/ 文件夹放入 .lua)", parent="script_list_container",
                     color=(150, 150, 150))
        return

    # 3. 动态创建复选框
    for name in script_names:
        is_active = name in enabled_scripts

        # 使用 group 方便排版 (这里做成两列布局)
        with dpg.group(horizontal=True, parent="script_list_container"):
            dpg.add_checkbox(
                label=f"{name}.lua",
                default_value=is_active,
                callback=update_script_state_callback,
                user_data=name
            )
            # 如果脚本在 enabled 列表里但文件不存在的特殊情况处理 (可选)
            if is_active:
                dpg.add_text("(已启用)", color=(0, 255, 0))
            else:
                dpg.add_text("(未启用)", color=(100, 100, 100))


# =================================================

def setup_chinese_font():
    with dpg.font_registry():
        font_path = r"C:\Windows\Fonts\msyh.ttc"
        if not os.path.exists(font_path): font_path = r"C:\Windows\Fonts\simhei.ttf"

        if os.path.exists(font_path):
            with dpg.font(font_path, 18) as font_cn:
                dpg.add_font_range(0x0020, 0x00FF)
                dpg.add_font_range(0x4E00, 0x9FA5)
            dpg.bind_font(font_cn)
        else:
            print("[GUI] ⚠ 未找到中文字体")


def create_gui():
    dpg.create_context()
    setup_chinese_font()

    with dpg.window(tag="Primary Window", label="AI 全参数配置管理器"):

        # === 顶部状态栏 ===
        with dpg.group(horizontal=True):
            dpg.add_button(label="💾 保存所有配置 (Save)", callback=save_callback, height=30, width=160)
            dpg.add_text("[就绪]", tag="status_text")

        dpg.add_separator()

        with dpg.tab_bar():

            # ================= TAB 1: 基础设置 =================
            with dpg.tab(label="基础 & 系统"):
                dpg.add_text("核心配置", color=(0, 255, 255))
                add_input_text("LICENSE_KEY", "许可证密钥 (License)")
                add_input_text("MODEL_PATH", "YOLO 模型路径")

                dpg.add_separator()
                dpg.add_text("系统性能", color=(0, 255, 255))
                add_bool("ENABLE_LOGGING", "启用日志记录")
                add_combo("LOG_LEVEL", "日志等级", ["DEBUG", "INFO", "WARNING", "ERROR"])
                add_bool("DEBUG_MODE", "调试模式 (显示画框)")
                add_int("CAPTURE_FPS", "截图帧率限制", 1, 500)
                add_int("INFERENCE_FPS", "推理帧率限制", 1, 500)
                add_int("CONFIG_MONITOR_INTERVAL_SEC", "配置热重载间隔 (秒)", 1, 60)

            # ================= TAB 2: 视觉识别 =================
            with dpg.tab(label="视觉识别"):
                dpg.add_text("检测参数", color=(100, 255, 100))
                add_float("CONF_THRESHOLD", "置信度阈值", 0.1, 0.99)
                add_float("IOU_THRESHOLD", "重叠剔除 (IOU)", 0.1, 0.99)
                add_int("CROP_SIZE", "推理区域大小 (Crop)", 160, 1280)

                dpg.add_separator()
                dpg.add_text("目标 ID 选择", color=(255, 255, 0))

                # 动态生成 ID 0-9 的复选框
                current_ids = cfg.get_config("TARGET_CLASS_IDS", [])
                for i in range(10):
                    if i % 5 == 0: group_tag = dpg.add_group(horizontal=True)
                    is_active = i in current_ids
                    dpg.add_checkbox(label=f"ID {i}", default_value=is_active, callback=update_class_ids_callback,
                                     user_data=i, parent=group_tag)
                    dpg.add_spacer(width=20, parent=group_tag)

                dpg.add_separator()
                dpg.add_text("优先级策略", color=(100, 255, 100))
                add_bool("ENABLE_HEAD_PRIORITY", "优先锁头")
                add_int("HEAD_CLASS_ID", "头部 ID 定义", 0, 10)
                add_float("HEAD_PRIORITY_BONUS", "头部权重加分", 0, 5000)

            # ================= TAB 3: PID 瞄准 =================
            with dpg.tab(label="PID 控制"):
                dpg.add_text("瞄准偏移", color=(100, 200, 255))
                add_float("AIM_Y_RATIO", "Y轴 瞄准高度 (0.5=中心)", 0.0, 1.0)
                add_float("AIM_X_OFFSET", "X轴 微调偏移", -100.0, 100.0)

                dpg.add_separator()
                dpg.add_text("PID 参数 (X 横向)", color=(100, 200, 255))
                add_float("PID_KP_X", "P (比例-速度)", 0.0, 5.0, speed=0.01)
                add_float("PID_KI_X", "I (积分-误差)", 0.0, 2.0, speed=0.001)
                add_float("PID_KD_X", "D (微分-阻尼)", 0.0, 1.0, speed=0.001)

                dpg.add_separator()
                dpg.add_text("PID 参数 (Y 纵向)", color=(100, 200, 255))
                add_float("PID_KP_Y", "P (比例-速度)", 0.0, 5.0, speed=0.01)
                add_float("PID_KI_Y", "I (积分-误差)", 0.0, 2.0, speed=0.001)
                add_float("PID_KD_Y", "D (微分-阻尼)", 0.0, 1.0, speed=0.001)

                dpg.add_separator()
                dpg.add_text("限制与死区", color=(100, 200, 255))
                add_int("MAX_SINGLE_MOVE_PX", "单帧最大移动像素", 1, 2000)
                add_int("PRECISION_DEAD_ZONE", "瞄准死区 (像素)", 0, 50)
                add_int("DEFAULT_DELAY_MS_PER_STEP", "每步延迟 (ms)", 0, 50)

            # ================= TAB 4: 追踪与滤波 =================
            with dpg.tab(label="追踪算法"):
                dpg.add_text("目标跟踪", color=(255, 100, 255))
                add_float("DISTANCE_WEIGHT", "距离权重系数", 0.0, 2.0)
                add_int("MIN_TARGET_LOCK_FRAMES", "锁定所需帧数", 1, 20)
                add_int("MAX_LOST_FRAMES", "丢失目标容忍帧", 1, 100)
                add_float("TARGET_SWITCH_THRESHOLD", "目标切换阈值", 0.01, 1.0)
                add_int("TARGET_IDENTITY_DISTANCE", "同目标判定距离", 10, 500)

                dpg.add_separator()
                dpg.add_text("卡尔曼滤波 (Kalman)", color=(255, 100, 255))
                add_bool("USE_KALMAN_FILTER", "启用卡尔曼滤波")
                add_float("KALMAN_PROCESS_NOISE", "过程噪声", 0.01, 10.0)
                add_float("KALMAN_MEASUREMENT_NOISE", "测量噪声", 0.1, 50.0)
                add_int("KALMAN_MAX_PREDICT_FRAMES", "最大预测帧数", 0, 10)

                dpg.add_separator()
                dpg.add_text("抗干扰 & 预判", color=(255, 100, 255))
                add_bool("ENABLE_LEAD_TARGET", "启用移动预判")
                add_int("LEAD_FRAMES", "预判提前量 (帧)", 0, 10)
                add_float("AIM_POINT_SMOOTH_ALPHA", "瞄准点平滑系数", 0.01, 1.0)
                add_int("CONFIDENCE_HISTORY_SIZE", "置信度历史长度", 1, 20)
                add_float("CONFIDENCE_DROP_THRESHOLD", "置信度骤降阈值", 0.01, 1.0)

            # ================= TAB 5: 压枪系统 =================
            with dpg.tab(label="压枪配置"):
                dpg.add_text("总开关", color=(255, 180, 0))
                add_bool("ENABLE_MANUAL_RECOIL", "启用压枪系统")
                add_bool("ENABLE_RECOIL_CONTROL", "启用后坐力控制")
                add_combo("MANUAL_RECOIL_TRIGGER_MODE", "触发按键模式", ["left_only", "both_buttons"])

                dpg.add_separator()
                dpg.add_text("触发逻辑", color=(255, 180, 0))
                add_bool("RECOIL_REQUIRE_TARGET", "仅在有目标时压枪")
                add_bool("RECOIL_REQUIRE_LOCK", "仅在锁定目标时压枪")
                add_float("RECOIL_TARGET_TIMEOUT", "目标丢失超时 (秒)", 0.1, 5.0)

                dpg.add_separator()
                dpg.add_text("压枪参数", color=(255, 180, 0))
                add_combo("RECOIL_PATTERN", "压枪模式", ["linear", "exponential", "custom"])
                add_float("RECOIL_VERTICAL_SPEED", "垂直下压速度", 0.0, 1000.0)
                add_float("RECOIL_HORIZONTAL_SPEED", "水平修正速度", -500.0, 500.0)
                add_float("RECOIL_INCREMENT_Y", "纵向递增系数", 0.0, 10.0)
                add_int("RECOIL_HORIZONTAL_VARIANCE", "水平随机抖动", 0, 50)

                dpg.add_separator()
                dpg.add_text("安全限制", color=(255, 180, 0))
                add_float("RECOIL_MAX_SINGLE_MOVE", "单次最大合力", 1.0, 500.0)
                add_float("RECOIL_MAX_SINGLE_MOVE_X", "X轴 最大单次", 1.0, 200.0)
                add_float("RECOIL_MAX_SINGLE_MOVE_Y", "Y轴 最大单次", 1.0, 200.0)

            # ================= TAB 6: 自动开火 =================
            with dpg.tab(label="自动开火"):
                add_bool("ENABLE_AUTO_FIRE", "🔥 启用自动开火")
                add_bool("AUTO_FIRE_DEBUG_MODE", "自动开火调试")

                dpg.add_separator()
                dpg.add_text("触发阈值", color=(255, 100, 100))
                add_float("AUTO_FIRE_ACCURACY_THRESHOLD", "准星重合度 (0.1-1.0)", 0.1, 1.0)
                add_float("AUTO_FIRE_DISTANCE_THRESHOLD", "距离像素阈值", 1.0, 200.0)
                add_int("AUTO_FIRE_MIN_LOCK_FRAMES", "开火前需锁定帧数", 0, 20)

            # ================= TAB 7: 驱动与按键 =================
            with dpg.tab(label="驱动 & 按键"):
                dpg.add_text("鼠标驱动", color=(200, 200, 200))
                add_bool("USE_DRIVER_MODE", "使用硬件驱动 (罗技/KMBox等)")
                add_bool("MOUSE_MODE_AUTO_FALLBACK", "驱动失败自动回退")
                add_input_text("DRIVER_PATH", "驱动设备路径")
                add_int("MOUSE_REQUEST", "鼠标 Request Code", 0, 9999999)
                add_int("MAX_MICKEY", "鼠标移动量限制 (Mickey)", 100, 5000)

                dpg.add_separator()
                dpg.add_text("按键监控", color=(200, 200, 200))
                add_bool("ENABLE_LEFT_MOUSE_MONITOR", "监控左键")
                add_bool("ENABLE_RIGHT_MOUSE_MONITOR", "监控右键")
                add_int("KEY_MONITOR_INTERVAL_MS", "监控间隔 (ms)", 10, 1000)

                dpg.add_separator()
                dpg.add_text("按键映射 ID (谨慎修改)", color=(150, 150, 150))
                add_int("APP_MOUSE_LEFT_DOWN", "Left Down ID", 0, 100)
                add_int("APP_MOUSE_LEFT_UP", "Left Up ID", 0, 100)
                add_int("APP_MOUSE_RIGHT_DOWN", "Right Down ID", 0, 100)
                add_int("APP_MOUSE_RIGHT_UP", "Right Up ID", 0, 100)

            # ================= TAB 8: 脚本扩展 (全新升级) =================
            with dpg.tab(label="脚本扩展"):
                dpg.add_text("脚本执行设置", color=(255, 255, 0))
                add_bool("SCRIPT_AUTO_RELOAD", "脚本自动重载 (监听文件修改)")
                add_bool("SCRIPT_DEBUG_MODE", "脚本调试模式 (输出详细日志)")
                add_bool("SCRIPT_VERBOSE_LOGGING", "详细日志 (Verbose Logging)")
                add_bool("SCRIPT_AUTO_ASYNC", "自动异步模式 (Auto Async)")
                add_int("SCRIPT_TIMEOUT_MS", "脚本执行超时 (ms)", 1, 1000)
                add_int("SCRIPT_MAX_WORKERS", "最大执行线程数", 1, 16)

                dpg.add_separator()

                with dpg.group(horizontal=True):
                    dpg.add_text("可用脚本列表", color=(0, 255, 255))
                    dpg.add_button(label="🔄 刷新列表", callback=refresh_scripts_ui, small=True)

                dpg.add_text("勾选以启用脚本 (自动保存至配置)", color=(150, 150, 150))

                # === 脚本列表容器 ===
                # 这里是一个空容器，启动时和点击刷新时会动态填充
                dpg.add_group(tag="script_list_container")
                # ====================

    dpg.create_viewport(title='AI Config Ultimate v4.0', width=800, height=750)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("Primary Window", True)

    # 启动时自动刷新一次脚本列表
    refresh_scripts_ui()

    dpg.start_dearpygui()
    dpg.destroy_context()


# ================= 通用控件封装 =================

def add_float(key, label, min_v=0.0, max_v=1.0, speed=0.01):
    val = float(cfg.get_config(key, 0.0))
    dpg.add_drag_float(label=label, default_value=val, min_value=min_v, max_value=max_v, speed=speed,
                       callback=update_config_callback, user_data=key, width=280)


def add_int(key, label, min_v=0, max_v=100):
    val = int(cfg.get_config(key, 0))
    dpg.add_drag_int(label=label, default_value=val, min_value=min_v, max_value=max_v, callback=update_config_callback,
                     user_data=key, width=280)


def add_bool(key, label):
    val = bool(cfg.get_config(key, False))
    dpg.add_checkbox(label=label, default_value=val, callback=update_config_callback, user_data=key)


def add_input_text(key, label):
    val = str(cfg.get_config(key, ""))
    dpg.add_input_text(label=label, default_value=val, callback=update_config_callback, user_data=key, width=280)


def add_combo(key, label, items):
    val = str(cfg.get_config(key, items[0]))
    if val not in items: items.append(val)
    dpg.add_combo(label=label, items=items, default_value=val, callback=update_config_callback, user_data=key,
                  width=280)


if __name__ == "__main__":
    create_gui()
