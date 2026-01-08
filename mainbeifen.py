# main.py (完整修复版 - 正确使用准星偏移量)

import math
import time
from threading import Event as ThreadEvent

import makcu_patch
from crosshair.threaded_crosshair_detector import ThreadedCrosshairDetector
from gui import stop_gui
from key_monitor.factory import get_monitored_keys, get_primary_trigger_key

makcu_patch.apply()

# 导入您的模块
import utils
from auto_fire_controller import AutoFireController
from config_manager import get_config, load_config, start_auto_reload, stop_auto_reload
from driver_loader import ensure_driver_loaded, unload_driver
from image.image_source import create_image_source
from key_monitor import create_key_monitor
from license_auth import LicenseAuthenticator
from mouse import create_mouse_controller, mouse_controller
from script_system import ScriptAPI, ScriptManager, EventSystem
from script_system.shared_game_state import get_game_state
from target_selector import TargetSelector
from utils import get_screen_info, calculate_capture_area
from yolo_detector import YOLOv8Detector
from crosshair.crosshair_manager import CrosshairManager

# 服务器信息
LICENSE_SERVER_URL = "http://1.14.184.43:45000"
LICENSE_SECRET_KEY = "your_secret_key_change_this"

_original_print = print
import atexit

def emergency_cleanup():
    """紧急清理：程序崩溃时抬起左键"""
    try:
        if 'mouse_controller' in globals() and mouse_controller:
            mouse_controller.mouse_up(mouse_controller.BUTTON_LEFT_UP)
            print("🆘 紧急抬起左键")
    except:
        pass

# 注册退出钩子
atexit.register(emergency_cleanup)

class AppState:
    """应用程序状态管理类（线程安全）"""

    def __init__(self):
        self.should_exit = ThreadEvent()
        self.mouse_control_active = ThreadEvent()
        self.right_mouse_pressed = ThreadEvent()
        self.left_mouse_pressed = ThreadEvent()

    def request_exit(self):
        self.should_exit.set()

    def is_exiting(self):
        return self.should_exit.is_set()

    def set_mouse_active(self, active: bool):
        if active:
            self.mouse_control_active.set()
        else:
            self.mouse_control_active.clear()

    def is_mouse_active(self):
        return self.mouse_control_active.is_set()

    def set_right_pressed(self, pressed: bool):
        if pressed:
            self.right_mouse_pressed.set()
        else:
            self.right_mouse_pressed.clear()

    def is_right_pressed(self):
        return self.right_mouse_pressed.is_set()

    def set_left_pressed(self, pressed: bool):
        if pressed:
            self.left_mouse_pressed.set()
        else:
            self.left_mouse_pressed.clear()

    def is_left_pressed(self):
        return self.left_mouse_pressed.is_set()


def heartbeat_worker(auth: LicenseAuthenticator, app_state: AppState):
    """后台发送心跳包"""
    heartbeat_interval = 30

    while auth.is_valid() and not app_state.is_exiting():
        if app_state.should_exit.wait(timeout=heartbeat_interval):
            break
        if app_state.is_exiting():
            break
        if not auth.send_heartbeat():
            utils.log(f"❌ 心跳验证失败！")
            utils.log("程序将在3秒后自动退出。")
            time.sleep(3)
            app_state.request_exit()
            break


class CachedConfig:
    """配置缓存类"""

    def __init__(self):
        self.recoil_require_target = None
        self.manual_recoil_trigger_mode = None
        self.enable_manual_recoil = None
        self.enable_auto_fire = None
        self.config_names = None
        self.config_ids = None
        self.crop_size = None
        self.recoil_vertical_speed = None
        self.auto_fire_distance_threshold = None
        self.auto_fire_accuracy_threshold = None
        self.inference_fps = None
        self.use_detected_crosshair = None  # ⭐ 新增
        self.crosshair_fallback_to_center = None  # ⭐ 新增
        self.refresh()

    def refresh(self):
        self.inference_fps = get_config("INFERENCE_FPS", 240)
        self.auto_fire_accuracy_threshold = get_config('AUTO_FIRE_ACCURACY_THRESHOLD', 0.75)
        self.auto_fire_distance_threshold = get_config('AUTO_FIRE_DISTANCE_THRESHOLD', 20.0)
        self.recoil_vertical_speed = get_config('RECOIL_VERTICAL_SPEED', 150.0)
        self.crop_size = get_config('CROP_SIZE', 640)
        self.config_ids = get_config('TARGET_CLASS_IDS', [])
        self.config_names = get_config('TARGET_CLASS_NAMES', [])
        self.enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
        self.enable_manual_recoil = get_config('ENABLE_MANUAL_RECOIL', False)
        self.manual_recoil_trigger_mode = get_config('MANUAL_RECOIL_TRIGGER_MODE', 'left_only')
        self.recoil_require_target = get_config('RECOIL_REQUIRE_TARGET', True)
        # ⭐ 新增配置项
        self.use_detected_crosshair = get_config('USE_DETECTED_CROSSHAIR', True)
        self.crosshair_fallback_to_center = get_config('CROSSHAIR_USE_FALLBACK_CENTER', True)


def run_gui_in_background():
    """后台运行 GUI"""
    from gui import create_gui
    create_gui()


def main():
    global frame_buffer, image_source, key_monitor, shared_makcu_controller, script_api, box, crosshair_manager, threaded_detector, gui_thread
    print("\n" + "=" * 60)
    print("正在初始化...")

    # 变量初始化
    auth = None
    app_state = AppState()
    heartbeat_thread = None
    use_driver_mode = False
    mouse_controller = None
    capture_process = None
    key_thread = None
    auto_fire = None
    stop_capture_event = None
    enable_auto_fire = False
    enable_manual_recoil = False
    script_manager = None
    preview_window = None
    game_state = get_game_state()

    # FPS 统计变量
    fps_history = []
    fps_max_samples = 30
    global image_source
    last_fps_time = time.perf_counter()

    try:
        import threading

        # 启动 GUI 线程
        gui_thread = threading.Thread(
            target=run_gui_in_background,
            daemon=False,
            name="GUI-Thread"
        )
        gui_thread.start()

        load_config(force_reload=True)
        start_auto_reload(interval_sec=2)
        utils.log("✅ 配置热重载已启动")

        use_makcu = get_config("USE_MAKCU", False)
        enable_left_monitor = get_config('ENABLE_LEFT_MOUSE_MONITOR', False)
        enable_right_monitor = get_config('ENABLE_RIGHT_MOUSE_MONITOR', True)
        enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
        poll_interval = get_config('KEY_MONITOR_INTERVAL_MS', 50) / 1000.0
        shared_makcu_controller = None

        if use_makcu:
            try:
                from makcu import create_controller

                utils.log("🔌 初始化 Makcu 硬件...")
                shared_makcu_controller = create_controller(
                    fallback_com_port=get_config("MAKCU_PORT", ""),
                    debug=get_config("MAKCU_DEBUG_MODE", False),
                    auto_reconnect=get_config("MAKCU_AUTO_RECONNECT", True)
                )

                time.sleep(0.5)

                if shared_makcu_controller.is_connected():
                    info = shared_makcu_controller.get_device_info()
                    utils.log(f"✅ Makcu 设备已连接: {info.get('version', 'Unknown')}")
                else:
                    utils.log("⚠ Makcu 连接失败，将降级到软件模式")
                    shared_makcu_controller = None
                    use_makcu = False

            except Exception as e:
                utils.log(f"❌ Makcu 初始化失败: {e}")
                shared_makcu_controller = None
                use_makcu = False

        key_monitor = create_key_monitor(
            app_state=app_state,
            use_makcu=use_makcu,
            shared_controller=shared_makcu_controller,
            enable_left=get_config('ENABLE_LEFT_MOUSE_MONITOR', False),
            enable_right=get_config('ENABLE_RIGHT_MOUSE_MONITOR', True),
            enable_mouse4=get_config('ENABLE_MOUSE4_MONITOR', False),
            enable_mouse5=get_config('ENABLE_MOUSE5_MONITOR', False),
            enable_auto_fire=get_config('ENABLE_AUTO_FIRE', False),
            poll_interval=get_config('KEY_MONITOR_INTERVAL_MS', 50) / 1000.0
        )

        if not key_monitor:
            utils.log("❌ 按键监控器创建失败")
            return

        if not key_monitor.start():
            utils.log("❌ 按键监控器启动失败")
            return

        # 驱动加载
        use_driver_mode = get_config("USE_DRIVER_MODE", True)

        if use_driver_mode:
            utils.log("正在自动加载驱动 (需要管理员权限)...")
            if not ensure_driver_loaded():
                utils.log("⚠ 驱动加载失败，尝试切换到 WinAPI 模式...")
                use_driver_mode = False
            else:
                utils.log("✅ 驱动已准备就绪")

        # 模式检查
        enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
        enable_manual_recoil = get_config('ENABLE_MANUAL_RECOIL', False)

        if enable_auto_fire and enable_manual_recoil:
            utils.log("\n❌ 错误：不能同时启用自动开火和手动压枪模式。")
            utils.log("请在 config.json 中只保留一个为 true。")
            return

        print("\n" + "=" * 60)
        print("🎮 FPS 助手启动成功，祝您游戏愉快！")
        print("=" * 60)

        # 核心组件初始化
        model = YOLOv8Detector()
        cached_config = CachedConfig()

        # 目标类别筛选
        if cached_config.config_ids:
            target_class_ids = [
                int(cid) for cid in cached_config.config_ids
                if int(cid) in model.names
            ]
            if target_class_ids:
                selected_names = [model.names[cid] for cid in target_class_ids]
                utils.log(f"✅ 已选择目标类别（ID）: {target_class_ids}")
                utils.log(f"   对应名称: {selected_names}")
            else:
                utils.log(f"⚠️ 警告：无效的类别 ID {cached_config.config_ids}")
        elif cached_config.config_names:
            target_class_ids = [
                class_id for class_id, class_name in model.names.items()
                if class_name in cached_config.config_names
            ]
            if target_class_ids:
                utils.log(f"✅ 已选择目标类别（名称）: {cached_config.config_names}")
                utils.log(f"   对应 ID: {target_class_ids}")
            else:
                utils.log(f"⚠️ 警告：未找到类名 {cached_config.config_names}，请检查配置")
        else:
            target_class_ids = list(model.names.keys())
            utils.log(f"⚠️ 未配置目标类别，将识别所有类别: {list(model.names.values())}")

        # 准星检测管理器
        crosshair_manager = None
        enable_crosshair = get_config('ENABLE_CROSSHAIR_DETECTION', False)

        if enable_crosshair:
            try:
                utils.log("\n" + "=" * 60)
                utils.log("🎯 正在初始化准星检测系统...")

                detector_type = get_config('CROSSHAIR_DETECTOR_TYPE', 'template')
                valorant_config = get_config('CROSSHAIR_VALORANT_CONFIG', '')

                crosshair_manager = CrosshairManager(
                    detector_type=detector_type,
                    valorant_config_code=valorant_config if valorant_config else None,
                    enable_detection=True
                )
                threaded_detector = ThreadedCrosshairDetector(crosshair_manager)
                threaded_detector.start()
                utils.log("✅ 准星检测系统初始化完成")
                utils.log(f"   检测器类型: {detector_type}")
                utils.log(f"   检测器信息: {crosshair_manager.get_detector_info()}")
                utils.log("=" * 60 + "\n")

            except Exception as e:
                utils.log(f"❌ 准星检测初始化失败: {e}")
                utils.log("   将继续运行（不影响核心功能）\n")
                crosshair_manager = None
                import traceback
                traceback.print_exc()
        else:
            utils.log("ℹ️ 准星检测未启用")

        # 鼠标控制器
        mouse_controller = create_mouse_controller(
            use_driver=use_driver_mode,
            use_makcu=use_makcu,
            shared_controller=shared_makcu_controller
        )

        # 屏幕信息
        screen_info = get_screen_info()
        screen_center_x = screen_info['width'] // 2
        screen_center_y = screen_info['height'] // 2
        capture_area = calculate_capture_area(cached_config.crop_size)
        target_selector = TargetSelector()

        # 自动开火控制器
        auto_fire = AutoFireController(
            mouse_controller=mouse_controller,
            key_monitor=key_monitor)

        if enable_manual_recoil:
            auto_fire.start_manual_recoil_monitor()
            utils.log("✅ 已启用手动压枪模式（需检测到目标 + 按键触发）")
        elif enable_auto_fire:
            utils.log("✅ 已启用自动开火模式")

        # 图像源初始化
        image_source = create_image_source()
        image_source.start()

        # 预览窗口初始化
        enable_preview = get_config('ENABLE_PREVIEW_WINDOW', False)

        if enable_preview:
            from preview_window import PreviewWindow

            preview_width = get_config('PREVIEW_WINDOW_WIDTH', 800)
            preview_height = get_config('PREVIEW_WINDOW_HEIGHT', 800)

            preview_window = PreviewWindow(
                window_name="YOLO Detection Preview",
                width=preview_width,
                height=preview_height
            )

        # 初始化脚本系统
        try:
            utils.log("\n" + "=" * 60)
            utils.log("🔧 正在初始化 Lua 脚本系统...")

            verbose_logging = get_config("SCRIPT_VERBOSE_LOGGING", False)
            event_system = EventSystem()

            def create_script_api():
                api = ScriptAPI(
                    mouse_controller=mouse_controller,
                    auto_fire_controller=auto_fire,
                    target_selector=target_selector,
                    yolo_detector=model,
                    screen_capture=None,
                    key_monitor=key_monitor,
                    verbose=verbose_logging
                )
                api.bind_app_state(app_state)
                return api

            script_api = ScriptAPI(
                mouse_controller=mouse_controller,
                auto_fire_controller=auto_fire,
                target_selector=None,
                yolo_detector=model,
                screen_capture=None,
                key_monitor=key_monitor,
                verbose=verbose_logging
            )
            script_api.bind_app_state(app_state)

            script_manager = ScriptManager(
                script_api_factory=create_script_api,
                event_system=event_system,
                scripts_dir="scripts"
            )
            script_manager.load_all_scripts()

            enabled_scripts = get_config("ENABLED_SCRIPTS", [])
            if enabled_scripts:
                utils.log(f"\n🟢 启用 {len(enabled_scripts)} 个脚本:")
                for script_name in enabled_scripts:
                    script_manager.enable_script(script_name)
            else:
                utils.log("\nℹ️ 未配置启用的脚本")

            utils.log("\n✅ Lua 脚本系统初始化完成")
            utils.log("=" * 60 + "\n")

        except Exception as e:
            utils.log(f"⚠️ 脚本系统初始化失败: {e}")
            utils.log("程序将继续运行（不影响核心功能）\n")
            script_manager = None

        if script_manager:
            script_api.target_selector = target_selector

        # 启动信息
        utils.log("\n" + "=" * 60)
        utils.log("🎯 FPS自瞄系统已启动")
        utils.log(f"🖱️ 鼠标控制: {mouse_controller.get_mode()} 模式")

        if enable_auto_fire:
            utils.log(f"🔫 自动开火: 已启用（按住右键触发）")
            utils.log(f"🎯 准确率阈值: {cached_config.auto_fire_accuracy_threshold * 100:.0f}%")
            utils.log(f"📏 距离阈值: {cached_config.auto_fire_distance_threshold:.1f}px")
        elif enable_manual_recoil:
            utils.log(f"⬇️ 手动压枪: 已启用（需目标确认）")
            utils.log(f"⚙️ 触发模式: {cached_config.manual_recoil_trigger_mode}")
            utils.log(f"🎯 需要目标: {cached_config.recoil_require_target}")

        utils.log(f"⬇️ 压枪速度: {cached_config.recoil_vertical_speed} px/s")
        utils.log(f"📍 屏幕中心: ({screen_center_x}, {screen_center_y})")
        utils.log(f"🎮 目标帧率: {cached_config.inference_fps} FPS")

        # ⭐ 新增：显示准星配置
        if enable_crosshair and cached_config.use_detected_crosshair:
            utils.log(f"🎯 准星模式: 使用检测到的准星位置")
            utils.log(f"   回退策略: {'启用' if cached_config.crosshair_fallback_to_center else '禁用'}")
        else:
            utils.log(f"🎯 准星模式: 使用屏幕中心")

        utils.log("=" * 60 + "\n")

        # 帧率控制参数
        target_fps = cached_config.inference_fps
        min_frame_time = 1.0 / target_fps if target_fps > 0 else 0
        last_frame_time = time.perf_counter()

        crosshair_position = None
        crosshair_stats_counter = 0
        crosshair_stats_interval = get_config('CROSSHAIR_STATS_INTERVAL', 300)

        # ⭐ 准星使用统计
        crosshair_used_count = 0
        fallback_used_count = 0

        # ⭐ 预检测启用的触发键
        enabled_trigger_keys = get_monitored_keys()
        primary_trigger_key = get_primary_trigger_key()

        if enable_auto_fire:
            if not enabled_trigger_keys:
                utils.log("⚠️ 警告：已启用自动开火，但没有启用任何按键监控！")
                utils.log("   请至少启用一个: ENABLE_RIGHT_MOUSE_MONITOR, ENABLE_LEFT_MOUSE_MONITOR, 等")
                enable_auto_fire = False  # 禁用自动开火
            else:
                key_names = {
                    'left': '左键', 'right': '右键',
                    'mouse4': '侧键4', 'mouse5': '侧键5'
                }
                utils.log(f"🎯 自动开火触发键: {[key_names[k] for k in enabled_trigger_keys]}")
                utils.log(f"   主触发键: {key_names[primary_trigger_key]}")
        # ==================== 主循环（完整修复版）====================
        while not app_state.is_exiting():
            frame_start = time.perf_counter()

            # ========== 1. 读取帧 ==========
            img_bgra = image_source.get_frame(timeout=0.001)
            if img_bgra is None:
                time.sleep(0.0001)
                continue

            # ========== 2. 模型推理 ==========
            results = model.predict(img_bgra)

            # ⭐⭐⭐ 3. 准星检测（多线程非阻塞）⭐⭐⭐
            fallback_center = (screen_center_x, screen_center_y) if cached_config.crosshair_fallback_to_center else None

            if crosshair_manager and crosshair_manager.enabled:
                # 提交帧到后台线程（非阻塞）
                threaded_detector.submit_frame(
                    img_bgra=img_bgra,
                    capture_area=capture_area,
                    fallback_center=fallback_center
                )

                # 立即获取最新结果（非阻塞）
                crosshair_position = threaded_detector.get_position(fallback_center)
            else:
                crosshair_position = None

            # ⭐⭐⭐ 核心修复：确定真实的瞄准参考点 ⭐⭐⭐
            if crosshair_position and cached_config.use_detected_crosshair:
                aim_reference_x = crosshair_position[0]
                aim_reference_y = crosshair_position[1]
            else:
                aim_reference_x = screen_center_x
                aim_reference_y = screen_center_y

            mouse_controller.update_crosshair_position(aim_reference_x, aim_reference_y)

            # ========== 4. 目标列表构建（使用真实准星位置）==========
            candidate_targets = []
            for result in results:
                if target_class_ids and result['class_id'] not in target_class_ids:
                    continue

                box = result['box']

                # 计算瞄准点（相对于捕获区域）
                target_x, target_y = target_selector.calculate_aim_point(
                    box, capture_area
                )

                center_x = capture_area['left'] + (box[0] + box[2]) // 2
                center_y = capture_area['top'] + (box[1] + box[3]) // 2

                width = box[2] - box[0]
                height = box[3] - box[1]

                class_id = result['class_id']
                class_name = model.names.get(class_id, 'unknown')

                # ⭐ 修复：使用真实准星位置计算距离
                distance_to_crosshair = math.sqrt(
                    (target_x - aim_reference_x) ** 2 +
                    (target_y - aim_reference_y) ** 2
                )

                candidate_targets.append({
                    'x': center_x,
                    'y': center_y,
                    'box': box,
                    'width': width,
                    'height': height,
                    'confidence': result['confidence'],
                    'class_id': class_id,
                    'class_name': class_name,
                    'distance': distance_to_crosshair,  # ⭐ 修复：使用真实距离
                    'aim_x': target_x,
                    'aim_y': target_y,
                })

            # ========== 5. 更新共享游戏状态 ==========
            game_state = get_game_state()
            game_state.update_targets(candidate_targets)

            if crosshair_position:
                game_state.has_crosshair = True
                game_state.crosshair_x = crosshair_position[0]
                game_state.crosshair_y = crosshair_position[1]
                game_state.crosshair_offset_x = crosshair_position[0] - screen_center_x
                game_state.crosshair_offset_y = crosshair_position[1] - screen_center_y
            else:
                game_state.has_crosshair = False

            # ========== 6. 目标选择（传入真实准星位置）==========
            best_x, best_y = target_selector.select_best_target(
                candidate_targets,
                screen_info['width'],
                screen_info['height'],
                reference_x=aim_reference_x,  # ⭐ 传入真实准星
                reference_y=aim_reference_y
            )

            # ========== 7. 计算真实FPS ==========
            current_time = time.perf_counter()
            delta = current_time - last_fps_time
            last_fps_time = current_time

            if delta > 0:
                current_fps = 1.0 / delta
                fps_history.append(current_fps)
                if len(fps_history) > fps_max_samples:
                    fps_history.pop(0)
                avg_fps = sum(fps_history) / len(fps_history)
            else:
                avg_fps = 0.0

            # ========== 8. 更新预览窗口 ==========
            if preview_window and preview_window.enabled:
                preview_window.update(
                    img=img_bgra,
                    results=results,
                    target_class_ids=target_class_ids,
                    best_target=(best_x, best_y) if best_x else None,
                    is_locked=target_selector.is_locked,
                    screen_center=(aim_reference_x, aim_reference_y),
                    class_names=model.names,
                    inference_fps=avg_fps,
                    crosshair_position=crosshair_position
                )

            # ========== 9. 鼠标控制（修复版）==========
            if app_state.is_mouse_active() and best_x is not None:
                # ⭐ 修复：基于真实准星位置判断是否需要移动
                if target_selector.should_send_command(
                        best_x, best_y, aim_reference_x, aim_reference_y
                ):
                    # ⭐ 修复：移动到目标位置（已经是绝对坐标）
                    mouse_controller.move_to_target(best_x, best_y)

            # ========== ⭐ 新增：自动开火核心逻辑 ==========
            if best_x is not None:
                offset_distance = math.sqrt(
                    (best_x - aim_reference_x) ** 2 +
                    (best_y - aim_reference_y) ** 2
                )

                # ⭐⭐⭐ 1. 更新目标状态（两种模式都需要！）⭐⭐⭐
                auto_fire.update_target_status(
                    detected=True,
                    locked=target_selector.is_locked,
                    lock_frames=target_selector.target_lock_frames,
                    distance=offset_distance
                )

                # ⭐⭐⭐ 2. 自动开火模式（主循环控制）⭐⭐⭐
                if enable_auto_fire:
                    trigger_pressed = any(
                        key_monitor.is_key_pressed(key) for key in enabled_trigger_keys
                    )

                    if trigger_pressed:
                        accuracy = auto_fire.update_accuracy(offset_distance)

                        if auto_fire.should_auto_fire(
                                target_locked=target_selector.is_locked,
                                lock_frames=target_selector.target_lock_frames,
                                current_accuracy=accuracy,
                                error_distance=offset_distance
                        ):
                            if not auto_fire.is_firing:
                                auto_fire.start_firing()
                            auto_fire.apply_recoil_control()
                        else:
                            if auto_fire.is_firing:
                                auto_fire.stop_firing()
                    else:
                        if auto_fire.is_firing:
                            auto_fire.stop_firing()
            else:
                # ⭐ 4. 目标丢失处理
                auto_fire.update_target_status(detected=False)
                if enable_auto_fire and auto_fire.is_firing:
                    auto_fire.stop_firing()

            # ========== 11. 脚本事件 ==========
            if script_manager:
                current_time = time.perf_counter()
                delta_time = current_time - last_frame_time
                last_frame_time = current_time

                game_state.current_fps = 1.0 / delta_time if delta_time > 0 else 0
                game_state.delta_time = delta_time
                game_state.frame_count += 1

                script_manager.call_event("onFrame", candidate_targets, delta_time)

    except KeyboardInterrupt:
        utils.log("\n⚠️ 用户中断")
    except Exception as e:
        utils.log(f"\n❌ 主程序发生致命错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # ==================== 资源清理 ====================
        utils.log("\n🧹 正在清理资源并安全退出...")
        app_state.request_exit()
        stop_auto_reload()

        if key_monitor:
            key_monitor.stop()

        # 1. 停止脚本系统
        if script_manager:
            try:
                utils.log("⏳ 正在停止脚本系统...")
                script_manager.stop()
                utils.log("✅ 脚本系统已停止")
            except Exception as e:
                utils.log(f"⚠️ 停止脚本系统时出错: {e}")

        # 2. 注销许可证
        if auth and auth.is_valid():
            utils.log("🔐 正在注销许可证...")
            try:
                auth.logout()
                utils.log("✅ 许可证已注销")
            except Exception as e:
                utils.log(f"⚠️ 注销许可证时出错: {e}")

        # ⭐ 3. 停止图像源（关键！）
        if 'image_source' in locals() and image_source:
            try:
                utils.log("⏳ 正在停止图像源...")
                image_source.stop()
                # 增加强制等待
                time.sleep(0.2)
                utils.log("✅ 图像源已停止")
            except Exception as e:
                utils.log(f"⚠️ 停止图像源时出错: {e}")

        # 4. 等待心跳线程（增加超时处理）
        if heartbeat_thread and heartbeat_thread.is_alive():
            utils.log("⏳ 等待心跳线程退出...")
            heartbeat_thread.join(timeout=1.0)
            if heartbeat_thread.is_alive():
                utils.log("⚠️ 心跳线程未在超时内退出")

        # 5. 等待按键监控线程
        if key_thread and key_thread.is_alive():
            utils.log("⏳ 等待按键监控线程退出...")
            key_thread.join(timeout=1.0)
            if key_thread.is_alive():
                utils.log("⚠️ 按键线程未在超时内退出")

        # 6. 停止自动开火
        if auto_fire:
            try:
                utils.log("⏳ 停止自动开火控制器...")
                if enable_auto_fire:
                    auto_fire.stop_firing()
                if enable_manual_recoil:
                    auto_fire.stop_manual_recoil_monitor()
                utils.log("✅ 自动开火已停止")
            except Exception as e:
                utils.log(f"⚠️ 停止自动开火时出错: {e}")
                try:
                    mouse_controller.mouse_up(mouse_controller.BUTTON_LEFT_UP)
                    utils.log("🆘 备用方案：已抬起左键")
                except:
                    pass

        if capture_process and capture_process.is_alive():
            utils.log("⏳ 等待捕获进程退出...")
            capture_process.join(timeout=2.0)
            if capture_process.is_alive():
                utils.log("⚠️ 捕获进程未响应，强制终止...")
                capture_process.terminate()
                capture_process.join(timeout=1.0)
                if capture_process.is_alive():
                    utils.log("⚠️ 捕获进程仍未退出，强制杀死...")
                    capture_process.kill()
                    capture_process.join(timeout=0.5)
        # ⭐ 新增：打印准星检测统计
        if crosshair_manager and crosshair_manager.enabled:
            try:
                utils.log("\n" + "=" * 60)
                utils.log("📊 准星检测最终统计")
                stats = crosshair_manager.get_stats()
                utils.log(f"  总检测帧数: {stats['total']}")
                utils.log(f"  成功帧数: {stats['success']}")
                utils.log(f"  成功率: {stats['success_rate']}")
                utils.log(f"  检测器类型: {stats['detector_type']}")
                utils.log("=" * 60 + "\n")
            except Exception as e:
                utils.log(f"⚠️ 打印准星统计时出错: {e}")
        # 9. 关闭鼠标控制器
        if mouse_controller:
            try:
                utils.log("⏳ 关闭鼠标控制器...")
                mouse_controller.close()
                utils.log("✅ 鼠标控制器已关闭")
            except Exception as e:
                utils.log(f"⚠️ 关闭鼠标控制器时出错: {e}")

        # 10. 卸载驱动
        if use_driver_mode:
            try:
                utils.log("⏳ 卸载驱动...")
                unload_driver(delete_service=False)
                utils.log("✅ 驱动已卸载")
            except Exception as e:
                utils.log(f"⚠️ 卸载驱动时出错: {e}")

        # ========== 🔥 8. 关闭 GUI（关键步骤）==========
        if preview_window:
            preview_window.close()

        if 'gui_thread' in locals() and gui_thread.is_alive():
            utils.log("⏳ 正在关闭 GUI 窗口...")
            stop_gui()  # 发送退出信号
            gui_thread.join(timeout=3)  # 等待最多 3 秒

            if gui_thread.is_alive():
                utils.log("⚠️ GUI 线程在 3 秒内未退出，可能存在问题")
            else:
                utils.log("✅ GUI 线程已正常退出")

        # ⭐ 11. 检查残留线程
        import threading
        active_threads = threading.enumerate()
        if len(active_threads) > 1:  # 主线程+残留线程
            utils.log(f"\n⚠️ 检测到 {len(active_threads) - 1} 个残留线程:")
            for t in active_threads:
                if t != threading.current_thread():
                    utils.log(f"   - {t.name} (daemon={t.daemon}, alive={t.is_alive()})")

        utils.log("\n✅ 程序已安全退出")

        # ⭐ 12. 强制退出（最后手段）
        time.sleep(0.5)  # 给日志输出时间
        import os
        os._exit(0)  # 强制退出所有线程


if __name__ == "__main__":
    main()
