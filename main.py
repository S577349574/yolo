# main.py
"""主程序入口（FPS游戏专用版 + 互斥压枪模式 + 右键触发自动开火）"""
import math
import queue as thread_queue
import time
from multiprocessing import Process, Queue, Event
from threading import Thread

import cv2
import win32api
import win32con

import utils
from config_manager import load_config, get_config, start_auto_reload
from yolo_detector import YOLOv8Detector
from mouse_controller import MouseController
from screen_capture import capture_screen
from target_selector import TargetSelector
from auto_fire_controller import AutoFireController
from utils import get_screen_info, calculate_capture_area


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

                # 🆕 更新右键状态（用于自动开火判断）
                right_mouse_pressed_list[0] = right_state

                if right_state and not right_mouse_pressed:
                    mouse_control_active_list[0] = True
                    if enable_auto_fire:
                        utils.log("▶ 已启用瞄准+自动开火 [鼠标右键按下]")
                    else:
                        utils.log("▶ 已启用瞄准 [鼠标右键按下]")
                    right_mouse_pressed = True
                elif not right_state and right_mouse_pressed:
                    mouse_control_active_list[0] = False
                    if enable_auto_fire:
                        utils.log("⏸ 已禁用瞄准+自动开火 [鼠标右键释放]")
                    else:
                        utils.log("⏸ 已禁用瞄准 [鼠标右键释放]")
                    right_mouse_pressed = False

            time.sleep(key_monitor_interval)

        except Exception as e:
            utils.log(f"[按键监控] 错误: {e}")
            break


def main():
    print("\n" + "=" * 60)
    print("正在初始化配置...")
    # ✅ 加载配置并验证路径
    try:
        load_config()

        config = load_config()
        print(f"配置加载成功，共 {len(config)} 项")
        start_auto_reload()

        # 验证关键文件
        model_path = get_config('MODEL_PATH')
        from pathlib import Path
        if not Path(model_path).exists():
            utils.log_debug(f"\n错误：模型文件不存在")
            utils.log_debug(f"期望路径: {model_path}")
            utils.log_debug(f"请确保将 onnx 放在 exe 所在目录")
            return

        utils.log(f"模型路径: {model_path}")

    except Exception as e:
        utils.log(f"配置加载失败: {e}")

    # 🆕 模式互斥检查
    enable_auto_fire = get_config('ENABLE_AUTO_FIRE', False)
    enable_manual_recoil = get_config('ENABLE_MANUAL_RECOIL', False)

    if enable_auto_fire and enable_manual_recoil:
        utils.log("\n错误：不能同时启用自动开火和手动压枪模式")
        utils.log("请在 config.json 中只保留一个为 true：")
        utils.log("  - ENABLE_AUTO_FIRE: 自动开火+自动压枪")
        utils.log("  - ENABLE_MANUAL_RECOIL: 手动射击+按键压枪")
        return

    print("启动成功，FPS游戏模式")
    print("=" * 60 + "\n")

    # 初始化YOLO模型
    try:
        model = YOLOv8Detector()
    except Exception as e:
        utils.log_debug(f"模型加载失败: {e}")
        return

    target_class_ids = [k for k, v in model.names.items() if v in get_config('TARGET_CLASS_NAMES')] if get_config(
        'TARGET_CLASS_NAMES') else []

    # 初始化鼠标控制器
    try:
        mouse_controller = MouseController()
    except Exception as e:
        utils.log_debug(f"鼠标控制器初始化失败: {e}")
        return

    # 初始化自动开火控制器
    auto_fire = AutoFireController(mouse_controller)

    # 🆕 根据模式启动对应功能
    if enable_manual_recoil:
        auto_fire.start_manual_recoil_monitor()
        utils.log("已启用手动压枪模式（按住左键时自动压枪）")
    elif enable_auto_fire:
        utils.log("已启用自动开火模式（需按住右键触发）")

    # 启动屏幕捕获进程
    frame_queue = Queue(maxsize=5)
    capture_ready_event = Event()
    capture_process = Process(target=capture_screen, args=(frame_queue, capture_ready_event, get_config('CROP_SIZE')))
    capture_process.start()

    capture_ready_event.wait(timeout=10)
    if not capture_ready_event.is_set():
        utils.log("捕获进程未就绪")
        capture_process.terminate()
        capture_process.join()
        mouse_controller.close()
        return

    # 获取屏幕信息
    screen_info = get_screen_info()
    screen_center_x = screen_info['width'] // 2
    screen_center_y = screen_info['height'] // 2
    capture_area = calculate_capture_area(get_config('CROP_SIZE'))

    # 初始化目标选择器
    target_selector = TargetSelector()

    # 🆕 控制变量（增加右键状态）
    mouse_control_active = [False]
    right_mouse_pressed = [False]  # 新增：右键按下状态
    should_exit = [False]

    # 启动按键监控线程
    key_thread = Thread(
        target=key_monitor,
        args=(mouse_control_active, right_mouse_pressed, should_exit),  # 传递右键状态
        daemon=True
    )
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

    try:
        frame_count = 0
        fps_start_time = time.time()
        last_inference_time = 0

        while not should_exit[0]:
            current_time = time.time()
            target_inference_fps = get_config("INFERENCE_FPS", 60)
            inference_interval = 1.0 / target_inference_fps

            # 帧率限制
            if current_time - last_inference_time < inference_interval:
                time.sleep(0.001)
                continue

            try:
                img_bgra = frame_queue.get(timeout=0.05)
            except thread_queue.Empty:
                continue

            # 颜色转换
            img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)

            # YOLO 推理
            results = model.predict(img_bgr)
            last_inference_time = current_time

            # 筛选目标类别
            candidate_targets = []
            for result in results:
                box = result['box']
                conf = result['confidence']
                cid = result['class_id']

                is_target_class = (not target_class_ids) or (cid in target_class_ids)
                if is_target_class:
                    target_x, target_y = target_selector.calculate_aim_point(box, capture_area)
                    candidate_targets.append({
                        'x': target_x,
                        'y': target_y,
                        'confidence': conf
                    })

            # 选择最佳目标
            best_x, best_y = target_selector.select_best_target(
                candidate_targets,
                screen_info['width'],
                screen_info['height']
            )

            # 计算误差距离和准确率
            current_accuracy = 0.0
            if best_x is not None:
                offset_distance = math.sqrt(
                    (best_x - screen_center_x) ** 2 +
                    (best_y - screen_center_y) ** 2
                )
                debug_distances.append(offset_distance)

                # 更新准确率
                current_accuracy = auto_fire.update_accuracy(offset_distance)
                # 🆕 自动开火模式逻辑（增加右键检查）
                if enable_auto_fire:
                    # 必须同时满足：右键按下 + 瞄准条件达标
                    if right_mouse_pressed[0] and auto_fire.should_auto_fire(
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
                # 目标丢失
                if enable_auto_fire and auto_fire.is_firing:
                    auto_fire.stop_firing()
                    auto_fire.reset()

            # 鼠标控制（瞄准）
            if mouse_control_active[0] and best_x is not None:
                if target_selector.should_send_command(best_x, best_y, screen_center_x, screen_center_y):
                    mouse_controller.move_to_target(best_x, best_y)
                    total_movements += 1
                else:
                    skipped_movements += 1

            # FPS显示
            frame_count += 1
            if time.time() - fps_start_time >= 1.0:
                fps = frame_count / (time.time() - fps_start_time)
                lock_status = '已锁定' if target_selector.is_locked else '搜索中'

                # 状态显示
                if enable_auto_fire:
                    # 🆕显示右键状态
                    right_key_status = '✓右键按下' if right_mouse_pressed[0] else '✗右键释放'
                    fire_status = '射击中' if auto_fire.is_firing else '⏸ 待命'
                    accuracy_percent = current_accuracy * 100
                    status_info = f"{fire_status} | {right_key_status} | 准确率: {accuracy_percent:.1f}%"
                elif enable_manual_recoil:
                    recoil_status = '⬇压枪中' if auto_fire.manual_recoil_active else '⏸ 待命'
                    status_info = f"{recoil_status}"
                else:
                    status_info = ""

                # 计算优化率
                efficiency = 0
                if total_movements + skipped_movements > 0:
                    efficiency = (skipped_movements / (total_movements + skipped_movements)) * 100

                stats = f"FPS: {fps:.1f} | 检测: {len(results)} | {lock_status} | {status_info} | " \
                        f"移动: {total_movements} | 跳过: {skipped_movements} | 优化率: {efficiency:.1f}%"

                # 距离统计
                if debug_distances:
                    avg_dist = sum(debug_distances) / len(debug_distances)
                    max_dist = max(debug_distances)
                    min_dist = min(debug_distances)
                    stats += f" | 偏移: 平均{avg_dist:.1f}px 最小{min_dist:.1f}px 最大{max_dist:.1f}px"

                utils.log(stats)

                # 重置计数器
                frame_count = 0
                fps_start_time = time.time()
                total_movements = 0
                skipped_movements = 0
                debug_distances.clear()

    except KeyboardInterrupt:
        utils.log("\n用户中断")
    finally:
        # 清理资源
        if enable_auto_fire:
            auto_fire.stop_firing()
        if enable_manual_recoil:
            auto_fire.stop_manual_recoil_monitor()

        should_exit[0] = True
        key_thread.join(timeout=2.0)
        capture_process.terminate()
        capture_process.join()
        mouse_controller.close()
        utils.log("\n程序已安全退出")


if __name__ == "__main__":
    main()
