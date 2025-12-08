# main.py (适配新鼠标控制器架构 + 智能压枪 - 修复优化版)
"""
主程序入口（FPS游戏专用版 + 互斥压枪模式 + 右键触发自动开火）
集成了在线许可证验证系统，服务器信息已内部硬编码。

修复内容：
1. 变量作用域问题（enable_auto_fire/enable_manual_recoil 提前声明）
2. 使用 threading.Event 替代列表（更安全）
3. 添加左键监听逻辑
4. 优化主循环时间控制
5. 缓存热点配置减少 get_config 调用
"""
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

# ⭐ 使用新的工厂函数导入
from mouse import create_mouse_controller

# ⭐️ 1. 将服务器信息安全地硬编码在程序内部
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
    """
    全局按键监控（功能键模式）

    Args:
        app_state: 应用程序状态对象
    """
    enable_left_monitor = get_config('ENABLE_LEFT_MOUSE_MONITOR', False)
    enable_right_monitor = get_config('ENABLE_RIGHT_MOUSE_MONITOR', True)
    enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
    key_monitor_interval = get_config('KEY_MONITOR_INTERVAL_MS', 50) / 1000.0

    # 按键状态追踪（用于边缘检测）
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
            # 使用 GetAsyncKeyState 检测按键状态
            f12_down = win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000
            left_down = bool(win32api.GetAsyncKeyState(0x01) & 0x8000)  # 左键
            right_down = bool(win32api.GetAsyncKeyState(0x02) & 0x8000)  # 右键

            # F12 退出
            if f12_down:
                app_state.request_exit()
                break

            # ⭐ 左键控制逻辑（修复：添加完整实现）
            if enable_left_monitor:
                app_state.set_left_pressed(left_down)

                # 边缘检测：按下时激活
                if left_down and not left_was_pressed:
                    app_state.set_mouse_active(True)
                # 边缘检测：释放时取消（仅当右键也未按下时）
                elif not left_down and left_was_pressed:
                    if not (enable_right_monitor and right_down):
                        app_state.set_mouse_active(False)

                left_was_pressed = left_down

            # 右键控制逻辑
            if enable_right_monitor:
                app_state.set_right_pressed(right_down)

                # 边缘检测：按下时激活
                if right_down and not right_was_pressed:
                    app_state.set_mouse_active(True)
                # 边缘检测：释放时取消（仅当左键也未按下时）
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
    heartbeat_interval = 30  # 秒

    while auth.is_valid() and not app_state.is_exiting():
        # 使用 wait 替代 sleep，可以更快响应退出信号
        if app_state.should_exit.wait(timeout=heartbeat_interval):
            break  # 收到退出信号

        if app_state.is_exiting():
            break

        if not auth.send_heartbeat():
            utils.log(f" 心跳验证失败！")
            utils.log("程序将在3秒后自动退出。")
            time.sleep(3)
            app_state.request_exit()
            break


class CachedConfig:
    """配置缓存类，减少频繁的 get_config 调用"""

    def __init__(self):
        self.refresh()

    def refresh(self):
        """刷新所有缓存配置"""
        self.inference_fps = get_config("INFERENCE_FPS", 60)
        self.auto_fire_accuracy_threshold = get_config('AUTO_FIRE_ACCURACY_THRESHOLD', 0.75)
        self.auto_fire_distance_threshold = get_config('AUTO_FIRE_DISTANCE_THRESHOLD', 20.0)
        self.recoil_vertical_speed = get_config('RECOIL_VERTICAL_SPEED', 150.0)
        self.crop_size = get_config('CROP_SIZE', 640)
        self.target_class_names = get_config('TARGET_CLASS_NAMES', [])
        self.enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
        self.enable_manual_recoil = get_config('ENABLE_MANUAL_RECOIL', False)
        self.manual_recoil_trigger_mode = get_config('MANUAL_RECOIL_TRIGGER_MODE', 'both_buttons')
        self.recoil_require_target = get_config('RECOIL_REQUIRE_TARGET', True)


def main():
    print("\n" + "=" * 60)
    print("正在初始化...")

    # ⭐ 将所有变量初始化移到最外层，确保 finally 中可访问
    auth = None
    app_state = AppState()
    heartbeat_thread = None
    use_driver_mode = False
    mouse_controller = None
    capture_process = None
    key_thread = None
    auto_fire = None
    stop_capture_event = None

    # ⭐ 提前声明模式变量（解决作用域问题）
    enable_auto_fire = False
    enable_manual_recoil = False

    try:
        # ==================== 配置加载与验证 ====================
        load_config(force_reload=True)
        card_key = get_config('LICENSE_KEY', "").strip()

        if not card_key:
            utils.log("\n" + "=" * 60)
            utils.log("  许可证密钥 (LICENSE_KEY) 为空！")
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
            utils.log(f"  许可证验证失败: {message}")
            utils.log("请检查卡密是否正确、网络是否通畅或联系管理员。")
            input("按回车键退出...")
            return

        utils.log(f" 验证成功: {message}")
        utils.log(f" 过期时间: {auth.expire_date}")

        start_auto_reload()
        heartbeat_thread = Thread(
            target=heartbeat_worker,
            args=(auth, app_state),
            daemon=True,
            name="HeartbeatThread"
        )
        heartbeat_thread.start()
        utils.log(" 后台心跳与配置监控已启动")

        # ==================== 驱动加载 ====================
        use_driver_mode = get_config("USE_DRIVER_MODE", True)

        if use_driver_mode:
            utils.log("正在自动加载驱动 (需要管理员权限)...")
            if not ensure_driver_loaded():
                utils.log("  驱动加载失败，尝试切换到 WinAPI 模式...")
                use_driver_mode = False
            else:
                utils.log(" 驱动已准备就绪")

        if not use_driver_mode:
            utils.log(" 使用 WinAPI 模式（无需驱动）")

        # ==================== 模式检查 ====================
        # ⭐ 在这里赋值（确保在 try 块内）
        enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
        enable_manual_recoil = get_config('ENABLE_MANUAL_RECOIL', False)

        if enable_auto_fire and enable_manual_recoil:
            utils.log("\n错误：不能同时启用自动开火和手动压枪模式。")
            utils.log("请在 config.json 中只保留一个为 true。")
            return

        print("\n" + "=" * 60)
        print("FPS 助手启动成功，祝您游戏愉快！")
        print("=" * 60)

        # ==================== 核心组件初始化 ====================
        model = YOLOv8Detector()
        cached_config = CachedConfig()

        target_class_ids = [
            k for k, v in model.names.items()
            if v in cached_config.target_class_names
        ] if cached_config.target_class_names else []

        # 创建鼠标控制器
        mouse_controller = create_mouse_controller(use_driver=use_driver_mode)
        utils.log(f" 鼠标控制器模式: {mouse_controller.get_mode()}")

        # 自动开火控制器
        auto_fire = AutoFireController(mouse_controller)

        if enable_manual_recoil:
            auto_fire.start_manual_recoil_monitor()
            utils.log("已启用手动压枪模式（需检测到目标 + 按键触发）")
        elif enable_auto_fire:
            utils.log("已启用自动开火模式（需按住右键触发）")

        # ==================== 屏幕捕获进程 ====================
        frame_queue = Queue(maxsize=5)
        capture_ready_event = ProcessEvent()
        stop_capture_event = ProcessEvent()  # ⭐ 添加停止事件

        capture_process = Process(
            target=capture_screen,
            args=(frame_queue, capture_ready_event, cached_config.crop_size, stop_capture_event),
            name="CaptureProcess"
        )
        capture_process.start()

        capture_ready_event.wait(timeout=10)
        if not capture_ready_event.is_set():
            utils.log("错误：屏幕捕获进程启动超时。程序将退出。")
            app_state.request_exit()
            return

        # ==================== 屏幕信息 ====================
        screen_info = get_screen_info()
        screen_center_x = screen_info['width'] // 2
        screen_center_y = screen_info['height'] // 2
        capture_area = calculate_capture_area(cached_config.crop_size)
        target_selector = TargetSelector()

        # ==================== 按键监控线程 ====================
        key_thread = Thread(
            target=key_monitor,
            args=(app_state,),
            daemon=True,
            name="KeyMonitorThread"
        )
        key_thread.start()

        # ==================== 统计变量 ====================
        total_movements = 0
        skipped_movements = 0
        debug_distances = []

        # ==================== 启动信息 ====================
        utils.log("\n" + "=" * 60)
        utils.log("FPS自瞄系统已启动")
        utils.log(f"鼠标控制: {mouse_controller.get_mode()} 模式")

        if enable_auto_fire:
            utils.log(f"自动开火: 已启用（按住右键触发）")
            utils.log(f"准确率阈值: {cached_config.auto_fire_accuracy_threshold * 100:.0f}%")
            utils.log(f"距离阈值: {cached_config.auto_fire_distance_threshold:.1f}px")
        elif enable_manual_recoil:
            utils.log(f"手动压枪: 已启用（需目标确认）")
            utils.log(f"触发模式: {cached_config.manual_recoil_trigger_mode}")
            utils.log(f"需要目标: {cached_config.recoil_require_target}")

        utils.log(f"压枪速度: {cached_config.recoil_vertical_speed} px/s")
        utils.log(f"屏幕中心: ({screen_center_x}, {screen_center_y})")
        utils.log("=" * 60 + "\n")

        # ==================== 主循环 ====================
        frame_count = 0
        fps_start_time = time.perf_counter()  # ⭐ 使用 perf_counter 更精确
        last_inference_time = 0.0
        inference_interval = 1.0 / cached_config.inference_fps

        while not app_state.is_exiting():
            current_time = time.perf_counter()

            # ⭐ 更精确的帧率控制
            time_since_last = current_time - last_inference_time
            if time_since_last < inference_interval:
                # 短休眠以降低 CPU 使用率
                sleep_time = inference_interval - time_since_last - 0.001
                if sleep_time > 0:
                    time.sleep(sleep_time)
                continue

            # 获取帧
            try:
                img_bgra = frame_queue.get(timeout=0.05)
            except thread_queue.Empty:
                continue

            # 推理
            results = model.predict(img_bgra)
            last_inference_time = time.perf_counter()

            # ==================== 目标筛选 ====================
            candidate_targets = []
            for result in results:
                if target_class_ids and result['class_id'] not in target_class_ids:
                    continue
                target_x, target_y = target_selector.calculate_aim_point(
                    result['box'], capture_area
                )
                candidate_targets.append({
                    'x': target_x,
                    'y': target_y,
                    'confidence': result['confidence']
                })

            best_x, best_y = target_selector.select_best_target(
                candidate_targets,
                screen_info['width'],
                screen_info['height']
            )

            # ==================== 目标状态更新 ====================
            current_accuracy = 0.0
            offset_distance = float('inf')

            if best_x is not None:
                # 计算偏移距离
                offset_distance = math.sqrt(
                    (best_x - screen_center_x) ** 2 +
                    (best_y - screen_center_y) ** 2
                )
                debug_distances.append(offset_distance)
                current_accuracy = auto_fire.update_accuracy(offset_distance)

                # 更新目标状态（检测到目标）
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
                        auto_fire.apply_recoil_control()
                    else:
                        if auto_fire.is_firing:
                            auto_fire.stop_firing()
            else:
                # 更新目标状态（未检测到目标）
                auto_fire.update_target_status(
                    detected=False,
                    locked=False,
                    lock_frames=0,
                    distance=float('inf')
                )

                # 自动开火模式：目标丢失时停止射击
                if enable_auto_fire and auto_fire.is_firing:
                    auto_fire.stop_firing()
                    auto_fire.reset()

            # ==================== 鼠标移动控制 ====================
            if app_state.is_mouse_active() and best_x is not None:
                if target_selector.should_send_command(
                        best_x, best_y, screen_center_x, screen_center_y
                ):
                    mouse_controller.move_to_target(best_x, best_y)
                    total_movements += 1
                else:
                    skipped_movements += 1

            # ==================== FPS 统计与日志 ====================
            frame_count += 1
            elapsed = time.perf_counter() - fps_start_time

            if elapsed >= 1.0:
                fps = frame_count / elapsed
                lock_status = '已锁定' if target_selector.is_locked else '搜索中'
                target_status = '有目标' if best_x is not None else '无目标'

                # 状态信息
                status_info = ""
                if enable_auto_fire:
                    right_key_status = '✓右键' if app_state.is_right_pressed() else '✗右键'
                    fire_status = '🔫射击' if auto_fire.is_firing else '待命'
                    status_info = f"{fire_status} | {right_key_status} | 准度: {current_accuracy * 100:.1f}%"
                elif enable_manual_recoil:
                    if auto_fire.manual_recoil_active:
                        status_info = '⬇压枪中'
                    elif best_x is not None:
                        status_info = '🎯待触发'
                    else:
                        status_info = '等待目标'

                # 效率计算
                total_ops = total_movements + skipped_movements
                efficiency = (skipped_movements / total_ops * 100) if total_ops > 0 else 0

                stats = (
                    f"FPS: {fps:.1f} | "
                    f"目标: {len(results)} ({target_status}) | "
                    f"{lock_status} | "
                    f"{status_info} | "
                    f"优化率: {efficiency:.1f}%"
                )

                if debug_distances:
                    avg_dist = sum(debug_distances) / len(debug_distances)
                    stats += f" | 偏移: {avg_dist:.1f}px"

                utils.log(stats)

                # 重置统计
                frame_count = 0
                total_movements = 0
                skipped_movements = 0
                fps_start_time = time.perf_counter()
                debug_distances.clear()

    except KeyboardInterrupt:
        utils.log("\n用户中断")
    except Exception as e:
        utils.log(f"\n主程序发生致命错误: {e}")
        traceback.print_exc()
    finally:
        # ==================== 资源清理 ====================
        utils.log("\n正在清理资源并安全退出...")
        app_state.request_exit()

        # 注销许可证
        if auth and auth.is_valid():
            utils.log("正在注销许可证...")
            try:
                auth.logout()
                utils.log("许可证已注销")
            except Exception as e:
                utils.log(f"注销许可证时出错: {e}")

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
                utils.log(f"停止自动开火时出错: {e}")

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
                utils.log(f"关闭鼠标控制器时出错: {e}")

        # 卸载驱动（仅驱动模式）
        if use_driver_mode:
            try:
                unload_driver(delete_service=False)
            except Exception as e:
                utils.log(f"[Driver] 卸载驱动时出现错误: {e}")

        utils.log("\n程序已安全退出")


if __name__ == "__main__":
    main()
