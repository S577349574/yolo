# main.py (适配 Lua 脚本系统 - 正确版本)

import math
import queue as thread_queue
import time
from multiprocessing import Process, Queue, Event as ProcessEvent
from threading import Thread, Event as ThreadEvent
import traceback

import cv2
import win32api
import win32con

# 导入您的模块
import utils
from config_manager import load_config, get_config, start_auto_reload
from license_auth import LicenseAuthenticator
from yolo_detector import YOLOv8Detector
from screen_capture import capture_screen
from target_selector import TargetSelector
from auto_fire_controller import AutoFireController
from utils import get_screen_info, calculate_capture_area
from driver_loader import ensure_driver_loaded, unload_driver
from mouse import create_mouse_controller

# ⭐ 导入脚本系统
from script_system import ScriptEngine, ScriptAPI, ScriptManager, EventSystem

# 服务器信息
LICENSE_SERVER_URL = "http://1.14.184.43:45000"
LICENSE_SECRET_KEY = "your_secret_key_change_this"


class AppState:
    """应用程序状态管理类（线程安全）"""

    def __init__(self):
        self.should_exit = ThreadEvent()
        self.mouse_control_active = ThreadEvent()
        self.right_mouse_pressed = ThreadEvent()
        self.left_mouse_pressed = ThreadEvent()

    def request_exit(self):
        """请求退出"""
        self.should_exit.set()

    def is_exiting(self):
        """是否正在退出"""
        return self.should_exit.is_set()

    def set_mouse_active(self, active: bool):
        """设置鼠标控制状态"""
        if active:
            self.mouse_control_active.set()
        else:
            self.mouse_control_active.clear()

    def is_mouse_active(self):
        """检查鼠标控制是否激活"""
        return self.mouse_control_active.is_set()

    def set_right_pressed(self, pressed: bool):
        """设置右键状态"""
        if pressed:
            self.right_mouse_pressed.set()
        else:
            self.right_mouse_pressed.clear()

    def is_right_pressed(self):
        """检查右键是否按下"""
        return self.right_mouse_pressed.is_set()

    def set_left_pressed(self, pressed: bool):
        """设置左键状态"""
        if pressed:
            self.left_mouse_pressed.set()
        else:
            self.left_mouse_pressed.clear()

    def is_left_pressed(self):
        """检查左键是否按下"""
        return self.left_mouse_pressed.is_set()


def key_monitor(app_state: AppState):
    """全局按键监控（功能键模式）"""
    enable_left_monitor = get_config('ENABLE_LEFT_MOUSE_MONITOR', False)
    enable_right_monitor = get_config('ENABLE_RIGHT_MOUSE_MONITOR', True)
    enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
    key_monitor_interval = get_config('KEY_MONITOR_INTERVAL_MS', 50) / 1000.0

    left_was_pressed = False
    right_was_pressed = False

    utils.log("\n[按键监控] 已启动全局监听（FPS游戏模式）")
    utils.log("  F12：退出程序")

    if enable_left_monitor:
        utils.log("  鼠标左键：按下启用瞄准，释放禁用瞄准")
    if enable_right_monitor:
        if enable_auto_fire:
            utils.log("  鼠标右键：按下启用瞄准并触发自动开火，释放禁用")
        else:
            utils.log("  鼠标右键：按下启用瞄准，释放禁用瞄准")

    while not app_state.is_exiting():
        try:
            f12_down = win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000
            left_down = bool(win32api.GetAsyncKeyState(0x01) & 0x8000)
            right_down = bool(win32api.GetAsyncKeyState(0x02) & 0x8000)

            if f12_down:
                app_state.request_exit()
                break

            if enable_left_monitor:
                app_state.set_left_pressed(left_down)

                if left_down and not left_was_pressed:
                    app_state.set_mouse_active(True)
                elif not left_down and left_was_pressed:
                    if not (enable_right_monitor and right_down):
                        app_state.set_mouse_active(False)

                left_was_pressed = left_down

            if enable_right_monitor:
                app_state.set_right_pressed(right_down)

                if right_down and not right_was_pressed:
                    app_state.set_mouse_active(True)
                elif not right_down and right_was_pressed:
                    if not (enable_left_monitor and left_down):
                        app_state.set_mouse_active(False)

                right_was_pressed = right_down

            time.sleep(key_monitor_interval)

        except Exception as e:
            utils.log(f"[按键监控] 错误: {e}")
            break


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
        """刷新所有缓存配置"""
        self.inference_fps = get_config("INFERENCE_FPS", 60)
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


def main():
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

    # ⭐ 脚本系统变量
    script_manager = None

    try:
        # ==================== 配置加载与验证 ====================
        load_config(force_reload=True)
        card_key = get_config('LICENSE_KEY', "").strip()

        if not card_key:
            utils.log("\n" + "=" * 60)
            utils.log("❌ 许可证密钥 (LICENSE_KEY) 为空！")
            utils.log("请打开程序目录下的 config.json 文件，")
            utils.log("在 \"LICENSE_KEY\" 字段中填入您的卡密。")
            utils.log("=" * 60)
            input("\n按回车键退出...")
            return

        print("\n" + "=" * 60)
        print("正在进行许可证验证...")
        auth = LicenseAuthenticator(LICENSE_SERVER_URL, LICENSE_SECRET_KEY)
        success, message = auth.verify(card_key)

        if not success:
            utils.log(f"❌ 许可证验证失败: {message}")
            utils.log("请检查卡密是否正确、网络是否通畅或联系管理员。")
            input("按回车键退出...")
            return

        utils.log(f"✅ 验证成功: {message}")
        utils.log(f"📅 过期时间: {auth.expire_date}")

        start_auto_reload()
        heartbeat_thread = Thread(
            target=heartbeat_worker,
            args=(auth, app_state),
            daemon=True,
            name="HeartbeatThread"
        )
        heartbeat_thread.start()
        utils.log("✅ 后台心跳与配置监控已启动")

        # ==================== 驱动加载 ====================
        use_driver_mode = get_config("USE_DRIVER_MODE", True)

        if use_driver_mode:
            utils.log("正在自动加载驱动 (需要管理员权限)...")
            if not ensure_driver_loaded():
                utils.log("⚠ 驱动加载失败，尝试切换到 WinAPI 模式...")
                use_driver_mode = False
            else:
                utils.log("✅ 驱动已准备就绪")

        if not use_driver_mode:
            utils.log("✅ 使用 WinAPI 模式（无需驱动）")

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
        mouse_controller = create_mouse_controller(use_driver=use_driver_mode)
        utils.log(f"✅ 鼠标控制器模式: {mouse_controller.get_mode()}")

        # 屏幕信息
        screen_info = get_screen_info()
        screen_center_x = screen_info['width'] // 2
        screen_center_y = screen_info['height'] // 2
        capture_area = calculate_capture_area(cached_config.crop_size)
        target_selector = TargetSelector()

        # 自动开火控制器
        auto_fire = AutoFireController(mouse_controller)

        if enable_manual_recoil:
            auto_fire.start_manual_recoil_monitor()
            utils.log("✅ 已启用手动压枪模式（需检测到目标 + 按键触发）")
        elif enable_auto_fire:
            utils.log("✅ 已启用自动开火模式（需按住右键触发）")

        # ⭐ ==================== 初始化脚本系统 ====================
        try:
            utils.log("\n" + "=" * 60)
            utils.log("🔧 正在初始化 Lua 脚本系统...")

            verbose_logging = get_config("SCRIPT_VERBOSE_LOGGING", False)
            # 1. 创建事件系统
            event_system = EventSystem()

            def create_script_api():
                """为每个脚本创建独立的 API 实例"""
                api = ScriptAPI(
                    mouse_controller=mouse_controller,
                    auto_fire_controller=auto_fire,
                    target_selector=target_selector,  # ⚠️ 确保这里不是 None
                    yolo_detector=model,
                    screen_capture=None,
                    verbose = verbose_logging  # ⭐ 传递配置
                )
                # ⭐ 在工厂函数中绑定 app_state（关键！）
                api.bind_app_state(app_state)
                return api
            # ⭐ 注意：这里需要传入你的真实对象
            script_api = ScriptAPI(
                mouse_controller=mouse_controller,
                auto_fire_controller=auto_fire,
                target_selector=None,  # 稍后会创建
                yolo_detector=model,
                screen_capture=None  # 捕获进程不在这里传递
            )

            script_api.bind_app_state(app_state)
            # 4. 创建脚本管理器
            script_manager = ScriptManager(
                script_api_factory=create_script_api,
                event_system=event_system,
                scripts_dir="scripts"
            )

            # 5. 加载所有脚本
            script_manager.load_all_scripts()

            enabled_scripts = get_config("ENABLED_SCRIPTS", [])
            if enabled_scripts:
                utils.log(f"\n🟢 启用 {len(enabled_scripts)} 个脚本:")
                for script_name in enabled_scripts:
                    script_manager.enable_script(script_name)
            else:
                utils.log("\nℹ️ 未配置启用的脚本")

            # ⭐ 单条成功日志
            utils.log("\n✅ Lua 脚本系统初始化完成")
            utils.log("=" * 60 + "\n")

        except Exception as e:
            utils.log(f"⚠️ 脚本系统初始化失败: {e}")
            if verbose_logging:
                import traceback
                utils.log(traceback.format_exc())
            utils.log("程序将继续运行（不影响核心功能）\n")
            script_manager = None
        # ==================== 屏幕捕获进程 ====================
        frame_queue = Queue(maxsize=5)
        capture_ready_event = ProcessEvent()
        stop_capture_event = ProcessEvent()

        capture_process = Process(
            target=capture_screen,
            args=(frame_queue, capture_ready_event, cached_config.crop_size, stop_capture_event),
            name="CaptureProcess"
        )
        capture_process.start()

        capture_ready_event.wait(timeout=10)
        if not capture_ready_event.is_set():
            utils.log("❌ 错误：屏幕捕获进程启动超时。程序将退出。")
            app_state.request_exit()
            return



        # ⭐ 更新 script_api 中的 target_selector
        if script_manager:
            script_api.target_selector = target_selector

        # 按键监控线程
        key_thread = Thread(
            target=key_monitor,
            args=(app_state,),
            daemon=True,
            name="KeyMonitorThread"
        )
        key_thread.start()

        # 统计变量
        total_movements = 0
        skipped_movements = 0
        debug_distances = []

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
        utils.log("=" * 60 + "\n")

        frame_count = 0
        fps_start_time = time.perf_counter()
        last_inference_time = 0.0
        last_frame_time = time.perf_counter()
        inference_interval = 1.0 / cached_config.inference_fps

        while not app_state.is_exiting():
            current_time = time.perf_counter()

            # 帧率控制
            sleep_time = inference_interval - (current_time - last_inference_time)
            if sleep_time > 0.001:
                time.sleep(sleep_time - 0.001)
                continue

            # 获取帧
            try:
                img_bgra = frame_queue.get(timeout=0.05)
            except thread_queue.Empty:
                continue

            # 推理
            results = model.predict(img_bgra)
            last_inference_time = time.perf_counter()

            candidate_targets = []
            for result in results:
                if target_class_ids and result['class_id'] not in target_class_ids:
                    continue

                # 计算瞄准点
                target_x, target_y = target_selector.calculate_aim_point(
                    result['box'], capture_area
                )

                # 提取边界框信息
                box = result['box']  # [x1, y1, x2, y2]
                width = box[2] - box[0]
                height = box[3] - box[1]

                # 获取类别名称
                class_id = result['class_id']
                class_name = model.names.get(class_id, 'unknown')
                distance_to_center = math.sqrt(
                    (target_x - screen_center_x) ** 2 +
                    (target_y - screen_center_y) ** 2
                )
                # 构建完整的目标数据
                candidate_targets.append({
                    'x': target_x,
                    'y': target_y,
                    'width': width,
                    'height': height,
                    'confidence': result['confidence'],
                    'class_id': class_id,
                    'class_name': class_name,
                    'distance': distance_to_center  # ⭐ 添加这个字段
                })

            best_x, best_y = target_selector.select_best_target(
                candidate_targets,
                screen_info['width'],
                screen_info['height']
            )

            # 目标状态更新
            current_accuracy = 0.0
            offset_distance = float('inf')

            if best_x is not None:
                offset_distance = math.sqrt(
                    (best_x - screen_center_x) ** 2 +
                    (best_y - screen_center_y) ** 2
                )
                current_accuracy = auto_fire.update_accuracy(offset_distance)

                auto_fire.update_target_status(
                    detected=True,
                    locked=target_selector.is_locked,
                    lock_frames=target_selector.target_lock_frames,
                    distance=offset_distance
                )

                # 自动开火模式逻辑
                if enable_auto_fire:
                    if app_state.is_right_pressed() and auto_fire.should_auto_fire(
                            target_selector.is_locked,
                            target_selector.target_lock_frames,
                            current_accuracy,
                            offset_distance
                    ):
                        if not auto_fire.is_firing:
                            auto_fire.start_firing()
                            if script_manager:
                                script_manager.call_event("onFireStart")

                        auto_fire.apply_recoil_control()
                    else:
                        if auto_fire.is_firing:
                            auto_fire.stop_firing()
                            if script_manager:
                                script_manager.call_event("onFireStop")
            else:
                auto_fire.update_target_status(
                    detected=False,
                    locked=False,
                    lock_frames=0,
                    distance=float('inf')
                )

                if enable_auto_fire and auto_fire.is_firing:
                    auto_fire.stop_firing()
                    auto_fire.reset()
                    if script_manager:
                        script_manager.call_event("onFireStop")

            # 鼠标移动控制
            if app_state.is_mouse_active() and best_x is not None:
                if target_selector.should_send_command(
                        best_x, best_y, screen_center_x, screen_center_y
                ):
                    mouse_controller.move_to_target(best_x, best_y)

            # ⭐ 触发脚本事件（所有调试信息由脚本处理）
            if script_manager:
                delta_time = current_time - last_frame_time
                last_frame_time = current_time
                script_manager.call_event("onFrame", candidate_targets, delta_time)

    except KeyboardInterrupt:
        utils.log("\n⚠️ 用户中断")
    except Exception as e:
        utils.log(f"\n❌ 主程序发生致命错误: {e}")
        traceback.print_exc()
    finally:
        # ==================== 资源清理 ====================
        utils.log("\n🧹 正在清理资源并安全退出...")
        app_state.request_exit()

        # ⭐ 停止脚本系统
        if script_manager:
            try:
                script_manager.stop()
                utils.log("✅ 脚本系统已停止")
            except Exception as e:
                utils.log(f"⚠️ 停止脚本系统时出错: {e}")

        # 注销许可证
        if auth and auth.is_valid():
            utils.log("🔐 正在注销许可证...")
            try:
                auth.logout()
                utils.log("✅ 许可证已注销")
            except Exception as e:
                utils.log(f"⚠️ 注销许可证时出错: {e}")

        # 等待心跳线程
        if heartbeat_thread and heartbeat_thread.is_alive():
            heartbeat_thread.join(timeout=2.0)

        # 等待按键监控线程
        if key_thread and key_thread.is_alive():
            key_thread.join(timeout=1.0)

        # 停止自动开火
        if auto_fire:
            try:
                if enable_auto_fire:
                    auto_fire.stop_firing()
                if enable_manual_recoil:
                    auto_fire.stop_manual_recoil_monitor()
            except Exception as e:
                utils.log(f"⚠️ 停止自动开火时出错: {e}")

        # 停止捕获进程
        if stop_capture_event:
            stop_capture_event.set()

        if capture_process and capture_process.is_alive():
            capture_process.join(timeout=2.0)
            if capture_process.is_alive():
                capture_process.terminate()
                capture_process.join(timeout=1.0)

        # 关闭鼠标控制器
        if mouse_controller:
            try:
                mouse_controller.close()
            except Exception as e:
                utils.log(f"⚠️ 关闭鼠标控制器时出错: {e}")

        # 卸载驱动
        if use_driver_mode:
            try:
                unload_driver(delete_service=False)
            except Exception as e:
                utils.log(f"⚠️ 卸载驱动时出现错误: {e}")

        utils.log("\n✅ 程序已安全退出")


if __name__ == "__main__":
    main()
