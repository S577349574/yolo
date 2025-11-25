# main.py (最终完整版 - 硬编码服务器信息)
"""
主程序入口（FPS游戏专用版 + 互斥压枪模式 + 右键触发自动开火）
集成了在线许可证验证系统，服务器信息已内部硬编码。
"""
import math
import queue as thread_queue
import time
from multiprocessing import Process, Queue, Event
from threading import Thread
import traceback
from pathlib import Path

import cv2
import win32api
import win32con

# 导入您的模块
import utils
from config_manager import load_config, get_config, start_auto_reload
from license_auth import LicenseAuthenticator
from yolo_detector import YOLOv8Detector
from mouse_controller import MouseController
from screen_capture import capture_screen
from target_selector import TargetSelector
from auto_fire_controller import AutoFireController
from utils import get_screen_info, calculate_capture_area
from driver_loader import ensure_driver_loaded, unload_driver

# ⭐️ 1. 将服务器信息安全地硬编码在程序内部
LICENSE_SERVER_URL = "http://1.14.184.43:45000"
LICENSE_SECRET_KEY = "your_secret_key_change_this"  # 强烈建议在发布前修改此密钥


def key_monitor(mouse_control_active_list, right_mouse_pressed_list, should_exit_list):
    """
    全局按键监控（功能键模式）
    - F12：退出
    - 鼠标左键/右键：控制瞄准开关（根据配置）
    - 右键状态：用于自动开火模式的触发条件
    """
    F12_PRESSED = False

    # 从配置中读取鼠标监视开关
    enable_left_monitor = get_config('ENABLE_LEFT_MOUSE_MONITOR', False)
    enable_right_monitor = get_config('ENABLE_RIGHT_MOUSE_MONITOR', True)
    enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
    key_monitor_interval = get_config('KEY_MONITOR_INTERVAL_MS', 50) / 1000.0

    # 初始化鼠标状态
    left_mouse_pressed = False
    right_mouse_pressed = False

    utils.log("\n[按键监控] 已启动全局监听（FPS游戏模式）")
    utils.log("  F12：退出程序")
    if enable_left_monitor:
        utils.log("  鼠标左键：按下启用瞄准，释放禁用瞄准")
    if enable_right_monitor:
        if enable_auto_fire:
            utils.log("  鼠标右键：按下启用瞄准并触发自动开火，释放禁用")
        else:
            utils.log("  鼠标右键：按下启用瞄准，释放禁用瞄准")

    while not should_exit_list[0]:
        try:
            f12_state = win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000

            # F12：退出
            if f12_state and not F12_PRESSED:
                should_exit_list[0] = True
                utils.log("正在退出程序... [F12]")
                break
            elif not f12_state:
                F12_PRESSED = False

            # 鼠标左键监视
            if enable_left_monitor:
                left_state = win32api.GetKeyState(0x01) < 0
                if left_state and not left_mouse_pressed:
                    mouse_control_active_list[0] = True
                    utils.log("▶ 已启用瞄准 [鼠标左键按下]")
                    left_mouse_pressed = True
                elif not left_state and left_mouse_pressed:
                    mouse_control_active_list[0] = False
                    utils.log("⏸ 已禁用瞄准 [鼠标左键释放]")
                    left_mouse_pressed = False

            # 鼠标右键监视
            if enable_right_monitor:
                right_state = win32api.GetKeyState(0x02) < 0
                right_mouse_pressed_list[0] = right_state

                if right_state and not right_mouse_pressed:
                    mouse_control_active_list[0] = True
                    log_msg = "▶ 已启用瞄准+自动开火" if enable_auto_fire else "▶ 已启用瞄准"
                    utils.log(f"{log_msg} [鼠标右键按下]")
                    right_mouse_pressed = True
                elif not right_state and right_mouse_pressed:
                    mouse_control_active_list[0] = False
                    log_msg = "⏸ 已禁用瞄准+自动开火" if enable_auto_fire else "⏸ 已禁用瞄准"
                    utils.log(f"{log_msg} [鼠标右键释放]")
                    right_mouse_pressed = False

            time.sleep(key_monitor_interval)

        except Exception as e:
            utils.log(f"[按键监控] 错误: {e}")
            break


def heartbeat_worker(auth: LicenseAuthenticator, should_exit_list: list):
    """后台发送心跳包，验证失败时设置退出标志"""
    while auth.is_valid() and not should_exit_list[0]:
        time.sleep(30)
        if should_exit_list[0]:
            break
        if not auth.send_heartbeat():
            utils.log(f"❌ 心跳验证失败！可能是卡密已到期、被封禁或在其他设备登录。")
            utils.log("程序将在3秒后自动退出。")
            time.sleep(3)
            should_exit_list[0] = True
            break


def main():
    print("\n" + "=" * 60)
    print("正在初始化...")
    auth = None
    should_exit = [False]
    heartbeat_thread = None

    try:
        # ⭐️ 2. 加载配置并只获取用户填写的卡密
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

        # ⭐️ 3. 使用硬编码的服务器信息进行验证
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
        utils.log(f"   - 过期时间: {auth.expire_date}")

        # ⭐️ 4. 启动后台任务
        start_auto_reload()
        heartbeat_thread = Thread(target=heartbeat_worker, args=(auth, should_exit), daemon=True)
        heartbeat_thread.start()
        utils.log("✅ 后台心跳与配置监控已启动")

        # ⭐️ 4.5 自动加载驱动（替代手动 InstDrv）
        utils.log("正在自动加载驱动 (需要管理员权限)...")
        if not ensure_driver_loaded():
            utils.log("❌ 驱动加载失败，请检查：")
            utils.log("   1) 当前程序是否以管理员身份运行")
            utils.log("   3) 驱动文件是否存在 / 是否可被系统加载")
            input("按回车键退出...")
            return
        utils.log("✅ 驱动已准备就绪")

    except Exception as e:
        utils.log(f"初始化或验证过程中发生严重错误: {e}")
        traceback.print_exc()
        input("按回车键退出...")
        return



    # 模式互斥检查
    enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
    enable_manual_recoil = get_config('ENABLE_MANUAL_RECOIL', False)

    if enable_auto_fire and enable_manual_recoil:
        utils.log("\n错误：不能同时启用自动开火和手动压枪模式。")
        utils.log("请在 config.json 中只保留一个为 true。")
        return

    print("\n" + "=" * 60)
    print("FPS 助手启动成功，祝您游戏愉快！")
    print("=" * 60)

    # 定义需要在finally中清理的资源
    mouse_controller, capture_process, key_thread, auto_fire = None, None, None, None

    try:
        # 初始化核心组件
        model = YOLOv8Detector()
        target_class_ids = [k for k, v in model.names.items() if v in get_config('TARGET_CLASS_NAMES')] if get_config(
            'TARGET_CLASS_NAMES') else []
        mouse_controller = MouseController()
        auto_fire = AutoFireController(mouse_controller)

        if enable_manual_recoil:
            auto_fire.start_manual_recoil_monitor()
            utils.log("已启用手动压枪模式（按住左键时自动压枪）")
        elif enable_auto_fire:
            utils.log("已启用自动开火模式（需按住右键触发）")

        frame_queue = Queue(maxsize=5)
        capture_ready_event = Event()
        capture_process = Process(target=capture_screen,
                                  args=(frame_queue, capture_ready_event, get_config('CROP_SIZE')))
        capture_process.start()

        capture_ready_event.wait(timeout=10)
        if not capture_ready_event.is_set():
            utils.log("错误：屏幕捕获进程启动超时。程序将退出。")
            should_exit[0] = True

        screen_info = get_screen_info()
        screen_center_x = screen_info['width'] // 2
        screen_center_y = screen_info['height'] // 2
        capture_area = calculate_capture_area(get_config('CROP_SIZE'))
        target_selector = TargetSelector()

        mouse_control_active = [False]
        right_mouse_pressed = [False]

        key_thread = Thread(target=key_monitor, args=(mouse_control_active, right_mouse_pressed, should_exit),
                            daemon=True)
        key_thread.start()

        # 统计变量
        total_movements = 0
        skipped_movements = 0
        debug_distances = []

        utils.log("\n" + "=" * 60)
        utils.log("FPS自瞄系统已启动")
        if enable_auto_fire:
            utils.log(f"自动开火: 已启用（按住右键触发）")
            utils.log(f"准确率阈值: {get_config('AUTO_FIRE_ACCURACY_THRESHOLD', 0.75) * 100:.0f}%")
            utils.log(f"距离阈值: {get_config('AUTO_FIRE_DISTANCE_THRESHOLD', 20.0):.1f}px")
        elif enable_manual_recoil:
            utils.log(f"手动压枪: 已启用")
        utils.log(f"压枪速度: {get_config('RECOIL_VERTICAL_SPEED', 150.0)} px/s")
        utils.log(f"屏幕中心: ({screen_center_x}, {screen_center_y})")
        utils.log("=" * 60 + "\n")

        # 主循环
        frame_count = 0
        fps_start_time = time.time()
        last_inference_time = 0

        while not should_exit[0]:
            current_time = time.time()
            target_inference_fps = get_config("INFERENCE_FPS", 60)
            inference_interval = 1.0 / target_inference_fps

            if current_time - last_inference_time < inference_interval:
                time.sleep(0.001)
                continue

            try:
                img_bgra = frame_queue.get(timeout=0.05)
            except thread_queue.Empty:
                continue

            img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
            results = model.predict(img_bgr)
            last_inference_time = current_time

            candidate_targets = []
            for result in results:
                if (not target_class_ids) or (result['class_id'] in target_class_ids):
                    target_x, target_y = target_selector.calculate_aim_point(result['box'], capture_area)
                    candidate_targets.append({'x': target_x, 'y': target_y, 'confidence': result['confidence']})

            best_x, best_y = target_selector.select_best_target(candidate_targets, screen_info['width'],
                                                                screen_info['height'])

            current_accuracy = 0.0
            if best_x is not None:
                offset_distance = math.sqrt((best_x - screen_center_x) ** 2 + (best_y - screen_center_y) ** 2)
                debug_distances.append(offset_distance)
                current_accuracy = auto_fire.update_accuracy(offset_distance)

                if enable_auto_fire:
                    if right_mouse_pressed[0] and auto_fire.should_auto_fire(target_selector.is_locked,
                                                                             target_selector.target_lock_frames,
                                                                             current_accuracy, offset_distance):
                        if not auto_fire.is_firing: auto_fire.start_firing()
                        auto_fire.apply_recoil_control()
                    else:
                        if auto_fire.is_firing: auto_fire.stop_firing()
            else:
                if enable_auto_fire and auto_fire.is_firing:
                    auto_fire.stop_firing()
                    auto_fire.reset()

            if mouse_control_active[0] and best_x is not None:
                if target_selector.should_send_command(best_x, best_y, screen_center_x, screen_center_y):
                    mouse_controller.move_to_target(best_x, best_y)
                    total_movements += 1
                else:
                    skipped_movements += 1

            frame_count += 1
            if time.time() - fps_start_time >= 1.0:
                fps = frame_count / (time.time() - fps_start_time)
                lock_status = '已锁定' if target_selector.is_locked else '搜索中'

                status_info = ""
                if enable_auto_fire:
                    right_key_status = '✓右键' if right_mouse_pressed[0] else '✗右键'
                    fire_status = '🔥射击' if auto_fire.is_firing else '⏸待命'
                    status_info = f"{fire_status} | {right_key_status} | 准度: {current_accuracy * 100:.1f}%"
                elif enable_manual_recoil:
                    status_info = '⬇压枪' if auto_fire.manual_recoil_active else '⏸待命'

                efficiency = (skipped_movements / (total_movements + skipped_movements)) * 100 if (
                                                                                                              total_movements + skipped_movements) > 0 else 0
                stats = f"FPS: {fps:.1f} | 目标: {len(results)} | {lock_status} | {status_info} | 优化率: {efficiency:.1f}%"

                if debug_distances:
                    avg_dist = sum(debug_distances) / len(debug_distances)
                    stats += f" | 偏移: {avg_dist:.1f}px"

                utils.log(stats)

                frame_count, total_movements, skipped_movements = 0, 0, 0
                fps_start_time = time.time()
                debug_distances.clear()


    except KeyboardInterrupt:
        utils.log("\n用户中断")
    except Exception as e:
        utils.log(f"\n主程序发生致命错误: {e}")
        traceback.print_exc()
    finally:
        utils.log("\n正在清理资源并安全退出...")
        should_exit[0] = True
        if auth and auth.is_valid():
            utils.log("正在注销许可证...")
            auth.logout()
            utils.log("✅ 许可证已注销")

        if heartbeat_thread and heartbeat_thread.is_alive():
            heartbeat_thread.join(timeout=1.0)

        if key_thread and key_thread.is_alive():
            key_thread.join(timeout=1.0)

        if auto_fire:
            if get_config('ENABLE_AUTO_FIRE'): auto_fire.stop_firing()
            if get_config('ENABLE_MANUAL_RECOIL'): auto_fire.stop_manual_recoil_monitor()

        if capture_process and capture_process.is_alive():
            capture_process.terminate()
            capture_process.join()

        if mouse_controller:
            mouse_controller.close()
        try:
            unload_driver(delete_service=False)
        except Exception as e:
            utils.log(f"[Driver] 卸载驱动时出现错误: {e}")
        utils.log("\n程序已安全退出")


if __name__ == "__main__":
    main()
