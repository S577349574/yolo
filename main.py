
import atexit
import math
import os
import threading
import time
from threading import Event as ThreadEvent, Thread

# === 模块导入 ===
import makcu_patch
from crosshair.threaded_crosshair_detector import ThreadedCrosshairDetector
from inference.manager import YOLOv8Detector
from key_monitor.factory import get_monitored_keys

makcu_patch.apply()

import utils
from mouse.auto_fire_controller import AutoFireController
import config_manager
from config_manager import get_config, load_config
import config_manager as cfg
from driver_loader import ensure_driver_loaded, unload_driver
from image.image_source import create_image_source
import traceback
from license_auth import LicenseAuthenticator  # ⭐ 新增：许可证验证
from mouse import create_mouse_controller
from script_system import ScriptAPI, ScriptManager, EventSystem
from script_system.shared_game_state import get_game_state
from target_manager.target_selector import TargetSelector
from utils import get_screen_info, calculate_capture_area
from crosshair.crosshair_manager import CrosshairManager

# ⭐ 服务器信息
LICENSE_SERVER_URL = "http://1.14.184.43:45000"
LICENSE_SECRET_KEY = "your_secret_key_change_this"

# 全局变量用于紧急清理 (atexit)
_core_instance = None


def emergency_cleanup():
    """紧急清理：程序崩溃时抬起左键"""
    try:
        if _core_instance and _core_instance.mouse_controller:
            _core_instance.mouse_controller.mouse_up(1)  # left up
            print("紧急抬起左键")
    except:
        pass


atexit.register(emergency_cleanup)


class AppState:
    """应用程序状态管理类（保留原有逻辑，对接新的 Event 系统）"""

    def __init__(self, stop_event):
        self._stop_event = stop_event  # 引用全局 stop_event
        self.mouse_control_active = ThreadEvent()
        self.right_mouse_pressed = ThreadEvent()
        self.left_mouse_pressed = ThreadEvent()

    def request_exit(self):
        self._stop_event.set()

    def is_exiting(self):
        return self._stop_event.is_set()

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


class CachedConfig:
    """配置缓存类"""

    def __init__(self):
        self.inference_fps = 240
        self.auto_fire_accuracy_threshold = 0.75
        self.auto_fire_distance_threshold = 20.0
        self.recoil_vertical_speed = 150.0
        self.crop_size = 640
        self.config_ids = []
        self.config_names = []
        self.enable_auto_fire = False
        self.enable_manual_recoil = False
        self.manual_recoil_trigger_mode = 'left_only'
        self.recoil_require_target = True
        self.use_detected_crosshair = True
        self.crosshair_fallback_to_center = True

        # === 功能开关标志（预计算）===
        self.feature_crosshair = False
        self.feature_auto_fire = False
        self.feature_manual_recoil = False
        self.feature_preview = False
        self.feature_scripts = False
        self.feature_game_state = False

        self.refresh()

    def refresh(self):
        """刷新所有配置（恢复运行或热重载时调用）"""
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
        self.use_detected_crosshair = get_config('USE_DETECTED_CROSSHAIR', True)
        self.crosshair_fallback_to_center = get_config('CROSSHAIR_USE_FALLBACK_CENTER', True)

        # === 计算功能开关 ===
        self.feature_crosshair = get_config('ENABLE_CROSSHAIR_DETECTION', False)
        self.feature_preview = get_config('ENABLE_PREVIEW_WINDOW', False)
        self.feature_manual_recoil = self.enable_manual_recoil

        self.feature_scripts = (
                get_config('ENABLE_SCRIPT_SYSTEM', True) and
                bool(get_config("ENABLED_SCRIPTS", []))
        )

        self.feature_game_state = self.feature_scripts

        if self.enable_auto_fire:
            self.feature_auto_fire = bool(get_monitored_keys())
        else:
            self.feature_auto_fire = False


def heartbeat_worker(auth: LicenseAuthenticator, app_state: AppState, stop_event: ThreadEvent):
    """
    ⭐ 后台心跳线程（适配新架构）

    Args:
        auth: 许可证验证器实例
        app_state: 应用状态对象
        stop_event: 停止事件（来自 config_manager）
    """
    heartbeat_interval = 30

    utils.log("心跳线程已启动")

    while auth.is_valid() and not stop_event.is_set():
        # 等待心跳间隔或停止信号
        if stop_event.wait(timeout=heartbeat_interval):
            break

        if stop_event.is_set():
            break

        # 发送心跳
        if not auth.send_heartbeat():
            utils.log("心跳验证失败！")
            utils.log("程序将在3秒后自动退出。")
            time.sleep(3)
            app_state.request_exit()
            break

    utils.log("心跳线程已停止")


class CoreService:
    """
    核心服务类：负责管理所有子系统的生命周期
    """

    def __init__(self):
        self.command_sender = None
        self.target_selector = None
        self.capture_area = None
        self.screen_info = None
        self.cached_config = None
        global _core_instance
        _core_instance = self

        # 1. 获取事件句柄
        self.resume_event, self.reload_event, self.stop_event = cfg.get_events()

        # 2. 状态对象
        self.app_state = AppState(self.stop_event)

        # 3. 组件占位符
        self.mouse_controller = None
        self.key_monitor = None
        self.image_source = None
        self.model = None
        self.script_manager = None
        self.crosshair_manager = None
        self.threaded_detector = None
        self.auto_fire = None
        self.preview_window = None
        self.shared_makcu_controller = None

        # ⭐ 许可证相关
        self.auth = None
        self.heartbeat_thread = None

    def verify_license(self) -> bool:
        """
        ⭐ 许可证验证（在资源加载前执行）

        Returns:
            bool: 验证是否成功
        """
        print("\n" + "=" * 60)
        print("正在进行许可证验证...")
        print("=" * 60)

        # 1. 读取卡密
        card_key = get_config('LICENSE_KEY', "").strip()

        if not card_key:
            utils.log("\n" + "=" * 60)
            utils.log("许可证密钥 (LICENSE_KEY) 为空！")
            utils.log("请打开程序目录下的 config.json 文件，")
            utils.log("在 \"LICENSE_KEY\" 字段中填入您的卡密。")
            utils.log("=" * 60)
            return False

        # 2. 验证许可证
        self.auth = LicenseAuthenticator(LICENSE_SERVER_URL, LICENSE_SECRET_KEY)
        success, message = self.auth.verify(card_key)

        if not success:
            utils.log(f"许可证验证失败: {message}")
            utils.log("请检查卡密是否正确、网络是否通畅或联系管理员。")
            self.auth = None
            return False

        utils.log(f"验证成功: {message}")
        utils.log(f"过期时间: {self.auth.expire_date}")

        # 3. 启动心跳线程
        self.heartbeat_thread = Thread(
            target=heartbeat_worker,
            args=(self.auth, self.app_state, self.stop_event),
            daemon=True,
            name="HeartbeatThread"
        )
        self.heartbeat_thread.start()
        utils.log("后台心跳已启动")

        return True

    def load_resources(self) -> bool:
        """资源初始化/重载"""
        print(f"\n{'=' * 60}")
        print("[Core] 正在初始化/重载资源...")

        try:
            # 1. 加载配置
            load_config(force_reload=True)
            self.cached_config = CachedConfig()

            try:
                from network.command_sender import CommandSender
                agent_ip = get_config("AGENT_IP", "192.168.10.1") # 从配置读取游戏机IP
                cmd_port = get_config("COMMAND_PORT", 27016)   # 默认 27016
                self.command_sender = CommandSender(target_host=agent_ip, target_port=cmd_port)
                utils.log(f"网络指令发送器已就绪 -> {agent_ip}:{cmd_port}")
            except Exception as e:
                utils.log(f"网络发送器初始化失败: {e}")
                self.command_sender = None

            # ========== 1. Makcu 硬件初始化 ==========
            use_makcu = get_config("USE_MAKCU", False)
            self.shared_makcu_controller = None
            if use_makcu:
                try:
                    from makcu import create_controller
                    utils.log("🔌 初始化 Makcu 硬件...")
                    self.shared_makcu_controller = create_controller(
                        fallback_com_port=get_config("MAKCU_PORT", ""),
                        debug=get_config("MAKCU_DEBUG_MODE", False),
                        auto_reconnect=get_config("MAKCU_AUTO_RECONNECT", True)
                    )
                    time.sleep(0.5)
                    if self.shared_makcu_controller.is_connected():
                        utils.log("Makcu 设备已连接")
                    else:
                        utils.log("Makcu 连接失败，将降级到软件模式")
                        self.shared_makcu_controller = None
                        use_makcu = False
                except Exception as e:
                    utils.log(f"Makcu 初始化失败: {e}")
                    use_makcu = False

            # ========== 2. MTKmbox 硬件初始化 ⭐ ==========
            use_mtkmbox = get_config("USE_MTKMBOX", False)
            self.shared_mtkmbox_device = None
            if use_mtkmbox:
                try:
                    from mtkmbox import MTKMBOX
                    utils.log("🔌 初始化 MTKmbox 硬件...")

                    port = get_config("MTKMBOX_PORT", "COM6")
                    vid = get_config("MTKMBOX_VID", 0x0416)
                    pid = get_config("MTKMBOX_PID", 0x5020)
                    debug = get_config("MTKMBOX_DEBUG_MODE", False)

                    self.shared_mtkmbox_device = MTKMBOX(
                        port=port,
                        vid=vid,
                        pid=pid,
                        debug=debug
                    )
                    time.sleep(0.3)

                    if self.shared_mtkmbox_device.is_connected():
                        utils.log(f"MTKmbox 设备已连接 (端口: {port})")
                    else:
                        utils.log("MTKmbox 连接失败，将降级到软件模式")
                        self.shared_mtkmbox_device = None
                        use_mtkmbox = False
                except Exception as e:
                    utils.log(f"MTKmbox 初始化失败: {e}")
                    import traceback
                    traceback.print_exc()
                    use_mtkmbox = False

            # ========== 3. 硬件互斥性检查 ⭐ 新增 ==========
            if use_makcu and use_mtkmbox:
                utils.log("⚠检测到同时启用 Makcu 和 MTKmbox，应用优先级规则...")
                utils.log("  优先级: MTKmbox > Makcu")
                utils.log("  保留 MTKmbox，禁用 Makcu")
                use_makcu = False
                if self.shared_makcu_controller:
                    try:
                        self.shared_makcu_controller.close()
                    except Exception:
                        pass
                    self.shared_makcu_controller = None

            # ========== 4. 按键监控初始化 ⭐ 更新 ==========
            from key_monitor import create_key_monitor

            self.key_monitor = create_key_monitor(
                app_state=self.app_state,
                use_makcu=use_makcu,
                use_mtkmbox=use_mtkmbox,
                shared_controller=self.shared_makcu_controller,
                shared_serial=self.shared_mtkmbox_device,
                enable_left=get_config('ENABLE_LEFT_MOUSE_MONITOR', False),
                enable_right=get_config('ENABLE_RIGHT_MOUSE_MONITOR', True),
                enable_mouse4=get_config('ENABLE_MOUSE4_MONITOR', False),
                enable_mouse5=get_config('ENABLE_MOUSE5_MONITOR', False),
                enable_auto_fire=self.cached_config.enable_auto_fire,
                poll_interval=get_config('KEY_MONITOR_INTERVAL_MS', 50) / 1000.0
            )

            if not self.key_monitor or not self.key_monitor.start():
                raise RuntimeError("按键监控器启动失败")

            if not self.key_monitor or not self.key_monitor.start():
                raise RuntimeError("按键监控器启动失败")

            print(f"[Debug] key_monitor 类型: {type(self.key_monitor).__name__}")
            print(f"[Debug] key_monitor.running: {getattr(self.key_monitor, '_running', 'N/A')}")

            # 4. 驱动加载
            use_driver_mode = get_config("USE_DRIVER_MODE", True)
            if use_driver_mode:
                if not ensure_driver_loaded():
                    utils.log("⚠ 驱动加载失败，切换到 WinAPI 模式")
                    use_driver_mode = False
                else:
                    utils.log("驱动已就绪")

            # 5. YOLO 模型
            if self.model is None:
                # 首次加载:创建单例
                self.model = YOLOv8Detector()
            else:
                # 重载时:显式调用 reload()
                utils.log("[推理] 重新加载模型配置...")
                self.model.reload()  # ⭐ 关键修改

            # 6. 准星检测
            if get_config('ENABLE_CROSSHAIR_DETECTION', False):
                try:
                    self.crosshair_manager = CrosshairManager(
                        detector_type=get_config('CROSSHAIR_DETECTOR_TYPE', 'template'),
                        valorant_config_code=get_config('CROSSHAIR_VALORANT_CONFIG', ''),
                        enable_detection=True,enable_smooth=False
                    )
                    crop_size = self.cached_config.crop_size
                    img_shape = (crop_size, crop_size, config_manager.get_config("FRAME_CHANNELS"))  # BGRA = 4 通道

                    # ✅ 传入 img_shape 参数
                    self.threaded_detector = ThreadedCrosshairDetector(
                        crosshair_manager=self.crosshair_manager,
                        img_shape=img_shape
                    )
                    self.threaded_detector.start()
                    utils.log("准星检测系统初始化完成")
                except Exception as e:
                    utils.log(f"准星检测初始化失败: {e}")
            else:
                self.crosshair_manager = None
                self.threaded_detector = None

            # 7. 鼠标控制器
            self.mouse_controller = create_mouse_controller(
                use_makcu=use_makcu,
                use_mtkmbox=use_mtkmbox,
                use_driver=get_config("USE_DRIVER_MODE", False),
                shared_makcu_controller=self.shared_makcu_controller,  # ⭐ 传递共享控制器
                shared_mtkmbox_device=self.shared_mtkmbox_device
            )

            if not self.mouse_controller:
                raise RuntimeError("鼠标控制器创建失败")

            # 8. 目标选择与屏幕参数
            self.screen_info = get_screen_info()
            self.capture_area = calculate_capture_area(self.cached_config.crop_size)
            self.target_selector = TargetSelector()

            # 9. 自动开火/压枪
            self.auto_fire = AutoFireController(self.mouse_controller, self.key_monitor)
            if self.cached_config.enable_manual_recoil:
                self.auto_fire.start_manual_recoil_monitor()
            elif self.cached_config.enable_auto_fire:
                if not get_monitored_keys():
                    utils.log("⚠ 自动开火已禁用：未配置触发键")
                    self.cached_config.enable_auto_fire = False

            # 10. 图像源
            self.image_source = create_image_source()
            self.image_source.start()

            # 11. 预览窗口
            if get_config('ENABLE_PREVIEW_WINDOW', False):
                from gui.preview_window import PreviewWindow
                self.preview_window = PreviewWindow(
                    window_name="YOLO Preview",
                    width=get_config('PREVIEW_WINDOW_WIDTH', 800),
                    height=get_config('PREVIEW_WINDOW_HEIGHT', 800)
                )

            # 12. 脚本系统
            if get_config("ENABLE_SCRIPT_SYSTEM", True):
                try:
                    event_system = EventSystem()

                    def create_script_api():
                        api = ScriptAPI(
                            mouse_controller=self.mouse_controller,
                            auto_fire_controller=self.auto_fire,
                            target_selector=self.target_selector,
                            yolo_detector=self.model,
                            screen_capture=None,
                            key_monitor=self.key_monitor,
                            command_sender=self.command_sender, # ✅ [修改] 注入网络发送器
                            verbose=get_config("SCRIPT_VERBOSE_LOGGING", False)
                        )
                        api.bind_app_state(self.app_state)
                        return api

                    self.script_manager = ScriptManager(
                        script_api_factory=create_script_api,
                        event_system=event_system,
                        scripts_dir="scripts"
                    )
                    self.script_manager.load_all_scripts()
                    enabled_config = get_config("ENABLED_SCRIPTS", [])
                    if isinstance(enabled_config, str):
                        scripts_to_enable = [s.strip() for s in enabled_config.split(',') if s.strip()]
                    else:
                        scripts_to_enable = enabled_config

                    # 循环启用每一个脚本
                    for script in scripts_to_enable:
                        self.script_manager.enable_script(script)

                    utils.log("脚本系统已加载")
                except Exception as e:
                    utils.log(f"脚本初始化失败: {e}")
            else:
                self.script_manager = None
                utils.log("ℹ脚本系统已禁用")

            print("[Core] 所有资源加载完成")
            return True

        except Exception as e:
            print(f"[Core] 资源加载严重错误: {e}")
            traceback.print_exc()
            return False

    def release_resources(self):
        """释放所有资源"""
        print("\n[Core] 正在释放资源...")

        # 1. 停止脚本
        if self.script_manager:
            try:
                self.script_manager.stop()
            except:
                pass
            self.script_manager = None

        # 2. 停止自动开火/压枪
        if self.auto_fire:
            try:
                self.auto_fire.stop_firing()
                self.auto_fire.stop_manual_recoil_monitor()
            except:
                pass
            self.auto_fire = None

        # 3. 停止按键监控
        if self.key_monitor:
            try:
                self.key_monitor.stop()
            except:
                pass
            self.key_monitor = None

        # 4. 停止图像源
        if self.image_source:
            try:
                self.image_source.stop()
                time.sleep(0.1)
            except:
                pass
            self.image_source = None

        # 5. 停止准星检测
        if self.threaded_detector:
            try:
                self.threaded_detector.stop()
            except:
                pass
            self.threaded_detector = None
            self.crosshair_manager = None

        # 6. 关闭鼠标
        if self.mouse_controller:
            try:
                self.mouse_controller.close()
            except:
                pass
            self.mouse_controller = None

        # 7. 预览窗口
        if self.preview_window:
            try:
                self.preview_window.close()
            except:
                pass
            self.preview_window = None

        # 8. Makcu 硬件
        if self.shared_makcu_controller:
            try:
                utils.log("[Core] 🔌 断开 Makcu 硬件连接...")
                self.shared_makcu_controller.disconnect()
                time.sleep(0.5)
            except Exception as e:
                utils.log(f"[Core] Makcu 断开异常: {e}")
            self.shared_makcu_controller = None

        self.target_selector = None

    def logout_license(self):
        """⭐ 注销许可证"""
        if self.auth and self.auth.is_valid():
            utils.log("正在注销许可证...")
            try:
                self.auth.logout()
                utils.log("许可证已注销")
            except Exception as e:
                utils.log(f"⚠注销许可证时出错: {e}")

        # 等待心跳线程退出
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            utils.log("等待心跳线程退出...")
            self.heartbeat_thread.join(timeout=2.0)
            if self.heartbeat_thread.is_alive():
                utils.log("⚠心跳线程未在超时内退出")

    def run(self):
        """核心服务线程入口 - 修复版"""
        print("[Core] 服务线程启动")

        # ⭐ 首先进行许可证验证
        if not self.verify_license():
            utils.log("[Core] 许可证验证失败，服务无法启动")
            self.stop_event.set()
            return

        # === 外层循环：生命周期管理 ===
        while not self.stop_event.is_set():

            # 1. 加载资源
            if not self.load_resources():
                utils.log("[Core] 资源加载失败，等待配置修复...")
                utils.log("[Core] 请在 GUI 中修改配置后点击「保存」再点击「重载」按钮")

                # ✅ 修复：使用超时等待，定期检查 stop_event
                while not self.stop_event.is_set():
                    # 每 2 秒检查一次 reload_event
                    if self.reload_event.wait(timeout=2.0):
                        self.reload_event.clear()
                        utils.log("[Core] 收到重载信号，尝试重新加载...")
                        break
                    # 超时后继续循环，可以响应 stop_event

                if self.stop_event.is_set():
                    break
                continue  # 重新尝试加载资源

            self.reload_event.clear()

            if not self.resume_event.is_set():
                utils.log("[Core] 资源就绪，等待 GUI 启动信号...")

            # === 预计算不变量 ===
            screen_center_x = self.screen_info['width'] // 2
            screen_center_y = self.screen_info['height'] // 2

            # === 本地变量缓存 ===
            _feature_crosshair = False
            _feature_auto_fire = False
            _feature_manual_recoil = False
            _feature_preview = False
            _feature_scripts = False
            _feature_game_state = False
            _target_fps = 240
            _need_refresh_flags = True

            last_fps_time = time.perf_counter()

            # === 内层循环：实时推理 ===
            while not self.stop_event.is_set() and not self.reload_event.is_set():

                # A. 暂停控制
                if not self.resume_event.is_set():
                    self.resume_event.wait()
                    if self.stop_event.is_set() or self.reload_event.is_set():
                        break
                    _need_refresh_flags = True

                # B. 刷新功能标志
                if _need_refresh_flags:
                    self.cached_config.refresh()

                    _feature_crosshair = (
                            self.cached_config.feature_crosshair and
                            self.threaded_detector is not None
                    )
                    _feature_auto_fire = self.cached_config.feature_auto_fire
                    _feature_manual_recoil = self.cached_config.feature_manual_recoil
                    _feature_preview = (
                            self.cached_config.feature_preview and
                            self.preview_window is not None
                    )
                    _feature_scripts = (
                            self.cached_config.feature_scripts and
                            self.script_manager is not None
                    )
                    _feature_game_state = self.cached_config.feature_game_state
                    _target_fps = self.cached_config.inference_fps

                    _need_refresh_flags = False

                    utils.log(f"[Core] 功能标志: 准星={_feature_crosshair}, "
                              f"自动开火={_feature_auto_fire}, 压枪={_feature_manual_recoil}, "
                              f"预览={_feature_preview}, 脚本={_feature_scripts}")

                try:
                    t0 = time.perf_counter()

                    # C. 获取图像
                    img_bgra = self.image_source.get_frame(timeout=0.001)
                    if img_bgra is None:
                        time.sleep(0.0001)
                        continue

                    # D. 准星检测
                    crosshair_pos = None
                    if _feature_crosshair:
                        fb_center = (
                            (screen_center_x, screen_center_y)
                            if self.cached_config.crosshair_fallback_to_center
                            else None
                        )
                        self.threaded_detector.submit_frame(img_bgra, self.capture_area, fb_center)
                        crosshair_pos = self.threaded_detector.get_position(fb_center)

                    # 确定瞄准参考点
                    if crosshair_pos and self.cached_config.use_detected_crosshair:
                        aim_ref_x, aim_ref_y = crosshair_pos
                    else:
                        aim_ref_x, aim_ref_y = screen_center_x, screen_center_y

                    self.mouse_controller.update_crosshair_position(aim_ref_x, aim_ref_y)

                    # E. YOLO 推理
                    results = self.model.predict(img_bgra)

                    # F. 构建目标列表
                    candidate_targets = []
                    target_class_ids = self.cached_config.config_ids

                    for result in results:
                        box = result['box']
                        target_x, target_y = self.target_selector.calculate_aim_point(box, self.capture_area)
                        dist = math.sqrt((target_x - aim_ref_x) ** 2 + (target_y - aim_ref_y) ** 2)

                        candidate_targets.append({
                            'x': self.capture_area['left'] + (box[0] + box[2]) // 2,
                            'y': self.capture_area['top'] + (box[1] + box[3]) // 2,
                            'box': box,
                            'width': box[2] - box[0],
                            'height': box[3] - box[1],
                            'confidence': result['confidence'],
                            'class_id': result['class_id'],
                            'class_name': self.model.names.get(result['class_id'], 'unknown'),
                            'distance': dist,
                            'aim_x': target_x,
                            'aim_y': target_y
                        })

                    # G. 游戏状态更新
                    if _feature_game_state:
                        game_state = get_game_state()
                        game_state.update_targets(candidate_targets)
                        game_state.has_crosshair = bool(crosshair_pos)
                        if crosshair_pos:
                            game_state.crosshair_x, game_state.crosshair_y = crosshair_pos

                    # H. 选择最佳目标
                    best_x, best_y = self.target_selector.select_best_target(
                        candidate_targets,
                        self.screen_info['width'],
                        self.screen_info['height'],
                        reference_x=aim_ref_x,
                        reference_y=aim_ref_y
                    )

                    # I. 鼠标移动
                    if self.app_state.is_mouse_active() and best_x is not None:
                        if self.target_selector.should_send_command(best_x, best_y, aim_ref_x, aim_ref_y):
                            self.mouse_controller.move_to_target(best_x, best_y)

                    # J. 自动开火/压枪
                    # ==================== 优化版本 ====================

                    # 1️⃣ 提前计算目标信息
                    has_target = best_x is not None
                    offset_dist = None
                    target_too_far = False

                    if has_target:
                        offset_dist = math.sqrt((best_x - aim_ref_x) ** 2 + (best_y - aim_ref_y) ** 2)

                        # ⭐ 距离预检查
                        max_effective_distance = get_config('MAX_EFFECTIVE_DISTANCE', 150.0)
                        target_too_far = offset_dist > max_effective_distance

                    # 2️⃣ 更新目标状态（仅在需要时）
                    if _feature_auto_fire or _feature_manual_recoil:
                        if has_target and not target_too_far:
                            self.auto_fire.update_target_status(
                                detected=True,
                                locked=self.target_selector.is_locked,
                                lock_frames=self.target_selector.target_lock_frames,
                                distance=offset_dist
                            )
                        else:
                            # ⭐ 仅在状态变化时更新
                            if self.auto_fire._target_detected:
                                self.auto_fire.update_target_status(detected=False)

                    # 3️⃣ 自动开火逻辑（独立处理）
                    if _feature_auto_fire and has_target and not target_too_far:
                        # ⭐ 缓存按键检查结果
                        current_time = time.time()
                        if not hasattr(self, '_last_key_check_time'):
                            self._last_key_check_time = 0.0
                            self._cached_trigger_pressed = False

                        # 每 50ms 检查一次按键（降低频率）
                        if current_time - self._last_key_check_time > 0.05:
                            enabled_keys = get_monitored_keys()
                            self._cached_trigger_pressed = any(
                                self.key_monitor.is_key_pressed(k) for k in enabled_keys
                            )
                            self._last_key_check_time = current_time

                        trigger_pressed = self._cached_trigger_pressed

                        if trigger_pressed:
                            # ⭐ 仅在按键按下时计算准确率
                            acc = self.auto_fire.update_accuracy(offset_dist)

                            if self.auto_fire.should_auto_fire(
                                    target_locked=self.target_selector.is_locked,
                                    lock_frames=self.target_selector.target_lock_frames,
                                    current_accuracy=acc,
                                    error_distance=offset_dist
                            ):
                                if not self.auto_fire.is_firing:
                                    self.auto_fire.start_firing()
                                self.auto_fire.apply_recoil_control()
                            else:
                                if self.auto_fire.is_firing:
                                    self.auto_fire.stop_firing()
                        else:
                            # 按键释放，停止开火
                            if self.auto_fire.is_firing:
                                self.auto_fire.stop_firing()

                    elif _feature_auto_fire:
                        # 目标丢失或过远，停止开火
                        if self.auto_fire.is_firing:
                            self.auto_fire.stop_firing()

                    # K. 预览窗口
                    current_time = time.perf_counter()
                    fps_val = 1.0 / (current_time - last_fps_time + 1e-6)
                    last_fps_time = current_time

                    if _feature_preview:
                        self.preview_window.update(
                            img=img_bgra,
                            results=results,
                            capture_area=self.capture_area,
                            target_class_ids=target_class_ids,
                            best_target=(best_x, best_y) if best_x else None,
                            is_locked=self.target_selector.is_locked,
                            screen_center=(aim_ref_x, aim_ref_y),
                            class_names=self.model.names,
                            inference_fps=fps_val,
                            crosshair_position=crosshair_pos
                        )

                    # L. 脚本事件
                    if _feature_scripts:
                        self.script_manager.call_event("onFrame", candidate_targets, 1.0 / fps_val)

                    # M. 帧率休眠控制
                    elapsed = time.perf_counter() - t0
                    if _target_fps > 0:
                        sleep_time = (1.0 / _target_fps) - elapsed
                        if sleep_time > 0:
                            time.sleep(sleep_time)

                except Exception as e:
                    print(f"[Core] 循环异常: {e}")
                    traceback.print_exc()
                    time.sleep(1)

            # === 内层循环结束 ===
            self.release_resources()

            if self.reload_event.is_set():
                print("[Core] 等待硬件释放...")
                time.sleep(1.0)

            if self.stop_event.is_set():
                break

            if self.reload_event.is_set():
                print("[Core] 正在执行热重载...")

        # ⭐ 退出时注销许可证
        self.logout_license()

        print("[Core] 服务线程退出")


def start_app():
    """程序入口"""
    # 导入 GUI (延迟导入，避免循环依赖)
    from gui.gui import create_gui

    # 1. 创建核心服务
    core = CoreService()

    # 2. 启动核心线程 (Daemon=True，主线程退出时自动结束)
    core_thread = threading.Thread(target=core.run, daemon=True, name="CoreThread")
    core_thread.start()

    # 3. 在主线程运行 GUI (DearPyGui 要求)
    try:
        create_gui()
    except KeyboardInterrupt:
        pass
    finally:
        print("[Main] GUI 关闭，正在停止核心服务...")
        cfg.get_events()[2].set()  # 发送 stop_event
        core_thread.join(timeout=5.0)  # ⭐ 增加超时时间，等待许可证注销

        # 强制卸载驱动
        if core.mouse_controller:
            try:
                core.mouse_controller.close()
            except:
                pass

        unload_driver(delete_service=False)

        print("[Main] 程序已彻底退出")
        os._exit(0)


if __name__ == "__main__":
    start_app()
