# main.py (修复版 - 解决FPS下降和GPU利用率低的问题)
import math
import time
from threading import Event as ThreadEvent

# 导入您的模块
import utils
from auto_fire_controller import AutoFireController
from config_manager import get_config
from driver_loader import ensure_driver_loaded, unload_driver
from image.image_source import create_image_source
from key_monitor import create_key_monitor
from license_auth import LicenseAuthenticator
from mouse import create_mouse_controller
from script_system import ScriptAPI, ScriptManager, EventSystem
from script_system.shared_game_state import get_game_state
from target_selector import TargetSelector
from utils import get_screen_info, calculate_capture_area
from yolo_detector import YOLOv8Detector
import threading
# 服务器信息
LICENSE_SERVER_URL = "http://1.14.184.43:45000"
LICENSE_SECRET_KEY = "your_secret_key_change_this"

_original_print = print

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
        self.refresh()

    def refresh(self):
        self.inference_fps = get_config("INFERENCE_FPS", 240)  # ⭐ 默认240
        self.auto_fire_accuracy_threshold = get_config('AUTO_FIRE_ACCURACY_THRESHOLD', 0.75)
        self.auto_fire_distance_threshold = get_config('AUTO_FIRE_DISTANCE_THRESHOLD', 20.0)
        self.recoil_vertical_speed = get_config('RECOIL_VERTICAL_SPEED', 150.0)
        self.crop_size = get_config('CROP_SIZE', 640)
        self.config_ids = get_config('TARGET_CLASS_IDS', [])
        self.config_names = get_config('TARGET_CLASS_NAMES', [])
        self.enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
        self.enable_manual_recoil = get_config('ENABLE_MANUAL_RECOIL', False)
        self.manual_recoil_trigger_mode = get_config('MANUAL_RECOIL_TRIGGER_MODE', 'both_buttons')
        self.recoil_require_target = get_config('RECOIL_REQUIRE_TARGET', True)

def run_gui_in_background():
    """后台运行 GUI"""
    from gui import create_gui
    create_gui()
def main():
    global frame_buffer, image_source, key_monitor, shared_makcu_controller
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
    # ⭐ FPS 统计变量
    fps_history = []
    fps_max_samples = 30
    global image_source
    last_fps_time = time.perf_counter()
    try:
        import threading
        # ⭐ 启动 GUI 线程（不阻塞主程序）
        gui_thread = threading.Thread(target=run_gui_in_background, daemon=True)
        gui_thread.start()
        # # ==================== 配置加载与验证 ====================
        # load_config(force_reload=True)
        # card_key = get_config('LICENSE_KEY', "").strip()
        #
        # if not card_key:
        #     utils.log("\n" + "=" * 60)
        #     utils.log("❌ 许可证密钥 (LICENSE_KEY) 为空！")
        #     utils.log("请打开程序目录下的 config.json 文件，")
        #     utils.log("在 \"LICENSE_KEY\" 字段中填入您的卡密。")
        #     utils.log("=" * 60)
        #     input("\n按回车键退出...")
        #     return
        #
        # print("\n" + "=" * 60)
        # print("正在进行许可证验证...")
        # auth = LicenseAuthenticator(LICENSE_SERVER_URL, LICENSE_SECRET_KEY)
        # success, message = auth.verify(card_key)
        #
        # if not success:
        #     utils.log(f"❌ 许可证验证失败: {message}")
        #     utils.log("请检查卡密是否正确、网络是否通畅或联系管理员。")
        #     input("按回车键退出...")
        #     return
        #
        # utils.log(f"✅ 验证成功: {message}")
        # utils.log(f"📅 过期时间: {auth.expire_date}")
        #
        # start_auto_reload()
        # heartbeat_thread = Thread(
        #     target=heartbeat_worker,
        #     args=(auth, app_state),
        #     daemon=True,
        #     name="HeartbeatThread"
        # )
        # heartbeat_thread.start()
        # utils.log("✅ 后台心跳与配置监控已启动")
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

        # ⭐ 创建监控器
        key_monitor = create_key_monitor(
            app_state=app_state,
            use_makcu=use_makcu,
            shared_controller=shared_makcu_controller,  # ⭐ 必须传递
            enable_left=get_config('ENABLE_LEFT_MOUSE_MONITOR', False),
            enable_right=get_config('ENABLE_RIGHT_MOUSE_MONITOR', True),
            enable_auto_fire=get_config('ENABLE_AUTO_FIRE', False),
            poll_interval=get_config('KEY_MONITOR_INTERVAL_MS', 50) / 1000.0
        )

        if not key_monitor:
            utils.log("❌ 按键监控器创建失败")
            return

        # ⭐ 启动监控
        if not key_monitor.start():
            utils.log("❌ 按键监控器启动失败")
            return

        # ==================== 驱动加载 ====================
        use_driver_mode = get_config("USE_DRIVER_MODE", True)

        if use_driver_mode:
            utils.log("正在自动加载驱动 (需要管理员权限)...")
            if not ensure_driver_loaded():
                utils.log("⚠ 驱动加载失败，尝试切换到 WinAPI 模式...")
                use_driver_mode = False
            else:
                utils.log("✅ 驱动已准备就绪")

        # ==================== 模式检查 ====================
        enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
        enable_manual_recoil = get_config('ENABLE_MANUAL_RECOIL', False)

        if enable_auto_fire and enable_manual_recoil:
            utils.log("\n❌ 错误：不能同时启用自动开火和手动压枪模式。")
            utils.log("请在 config.json 中只保留一个为 true。")
            return

        print("\n" + "=" * 60)
        print("🎮 FPS 助手启动成功，祝您游戏愉快！")
        print("=" * 60)

        # ==================== 核心组件初始化 ====================
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

        # 鼠标控制器
        mouse_controller = create_mouse_controller(
            use_driver=use_driver_mode,
            use_makcu=use_makcu,
            shared_controller=shared_makcu_controller  # ⭐ 传递共享实例
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
            utils.log("✅ 已启用自动开火模式（需按住右键触发）")
        # ==================== 图像源初始化（新） ====================

        image_source = create_image_source()
        image_source.start()

        # ⭐⭐⭐ 新增：预览窗口初始化 ⭐⭐⭐
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
        # ==================== 初始化脚本系统 ====================
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
                    verbose=verbose_logging
                )
                api.bind_app_state(app_state)
                return api

            script_api = ScriptAPI(
                mouse_controller=mouse_controller,
                auto_fire_controller=auto_fire,
                target_selector=None,
                yolo_detector=model,
                screen_capture=None
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
        utils.log("=" * 60 + "\n")

        # ⭐ 帧率控制参数
        target_fps = cached_config.inference_fps
        min_frame_time = 1.0 / target_fps if target_fps > 0 else 0
        last_frame_time = time.perf_counter()





        # ==================== 主循环（优化版） ====================
        while not app_state.is_exiting():
            frame_start = time.perf_counter()

            # ========== 1. 读取帧（非阻塞） ==========
            img_bgra = image_source.get_frame(timeout=0.001)
            if img_bgra is None:
                time.sleep(0.0001)
                continue


            # ========== 2. 模型推理 ==========
            results = model.predict(img_bgra)

            # ========== 3. 目标列表构建 ==========
            candidate_targets = []
            for result in results:
                if target_class_ids and result['class_id'] not in target_class_ids:
                    continue

                target_x, target_y = target_selector.calculate_aim_point(
                    result['box'], capture_area
                )

                box = result['box']
                width = box[2] - box[0]
                height = box[3] - box[1]

                class_id = result['class_id']
                class_name = model.names.get(class_id, 'unknown')
                distance_to_center = math.sqrt(
                    (target_x - screen_center_x) ** 2 +
                    (target_y - screen_center_y) ** 2
                )

                candidate_targets.append({
                    'x': target_x,
                    'y': target_y,
                    'width': width,
                    'height': height,
                    'confidence': result['confidence'],
                    'class_id': class_id,
                    'class_name': class_name,
                    'distance': distance_to_center,
                    # 可选：如果你在 calculate_aim_point 已经计算了更精确的瞄准点
                    'aim_x': target_x,
                    'aim_y': target_y,
                })

            # ⭐⭐⭐ 新增：更新共享游戏状态 - 目标列表 ⭐⭐⭐
            game_state = get_game_state()
            game_state.update_targets(candidate_targets)

            # ========== 4. 目标选择 ==========
            best_x, best_y = target_selector.select_best_target(
                candidate_targets,
                screen_info['width'],
                screen_info['height']
            )

            # ⭐⭐⭐ 计算真实FPS ⭐⭐⭐
            current_time = time.perf_counter()
            delta = current_time - last_fps_time
            last_fps_time = current_time

            if delta > 0:
                current_fps = 1.0 / delta
                fps_history.append(current_fps)
                if len(fps_history) > fps_max_samples:
                    fps_history.pop(0)

                # 计算平均FPS
                avg_fps = sum(fps_history) / len(fps_history)
            else:
                avg_fps = 0.0

            # ⭐⭐⭐ 更新预览窗口（传递真实FPS）⭐⭐⭐
            if preview_window and preview_window.enabled:
                preview_window.update(
                    img=img_bgra,
                    results=results,
                    target_class_ids=target_class_ids,
                    best_target=(best_x, best_y) if best_x else None,
                    is_locked=target_selector.is_locked,
                    screen_center=(screen_center_x, screen_center_y),
                    class_names=model.names,
                    inference_fps=avg_fps  # ⭐ 传递真实推理FPS
                )

            # ========== 5. 开火控制 ==========
            if best_x is not None:
                offset_distance = math.sqrt(
                    (best_x - screen_center_x) ** 2 +
                    (best_y - screen_center_y) ** 2
                )

                # ⭐ 可选：更新瞄准/开火状态（供脚本使用）
                game_state.is_aiming = app_state.is_mouse_active()
                game_state.is_firing = auto_fire.is_firing
                game_state.is_locked = target_selector.is_locked
                game_state.lock_frames = target_selector.target_lock_frames

                # 如果有压枪偏移，也可以更新
                if enable_manual_recoil or (enable_auto_fire and auto_fire.is_firing):
                    game_state.update_recoil_state(
                        active=True,
                        offset_x=auto_fire.total_offset_x if hasattr(auto_fire, 'total_offset_x') else 0,
                        offset_y=auto_fire.total_offset_y if hasattr(auto_fire, 'total_offset_y') else 0,
                        shot_count=auto_fire.shot_count if hasattr(auto_fire, 'shot_count') else 0
                    )
                else:
                    game_state.update_recoil_state(active=False)
            if preview_window and preview_window.enabled:
                continue_preview = preview_window.update(
                    img=img_bgra,
                    results=results,
                    target_class_ids=target_class_ids,
                    best_target=(best_x, best_y) if best_x else None,
                    is_locked=target_selector.is_locked,
                    screen_center=(screen_center_x, screen_center_y),
                    class_names=model.names
                )

                if not continue_preview:
                    preview_window = None  # 用户关闭窗口

            if app_state.is_mouse_active() and best_x is not None:
                if target_selector.should_send_command(
                        best_x, best_y, screen_center_x, screen_center_y
                ):
                    mouse_controller.move_to_target(best_x, best_y)
            # ========== 7. 脚本事件 ==========
            if script_manager:
                current_time = time.perf_counter()
                delta_time = current_time - last_frame_time
                last_frame_time = current_time

                # ⭐ 更新性能数据
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
        if preview_window:
            preview_window.close()
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
