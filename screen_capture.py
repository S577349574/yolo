# screen_capture.py (DXcam 优化版 - 修复版)
"""
屏幕捕获模块 - 使用 DXcam 高性能截图

修复内容：
1. 添加 stop_event 支持优雅退出
2. 追踪 camera 启动状态，避免未启动就 stop
3. 添加性能统计（可选）
4. 更好的错误处理和日志
"""
import os
import time
import traceback

import dxcam
import psutil

import config_manager
import utils


def capture_screen(frame_queue, capture_ready_event, crop_size, stop_event=None):
    """
    DXcam 高性能截图进程

    Args:
        frame_queue: 用于传递帧的队列
        capture_ready_event: 捕获就绪事件
        crop_size: 捕获区域大小
        stop_event: 停止事件（可选，用于优雅退出）
    """

    # 设置进程优先级
    try:
        p = psutil.Process(os.getpid())
        if os.name == 'nt':
            p.nice(psutil.HIGH_PRIORITY_CLASS)
            utils.log("[Capture] 进程优先级已设置为 HIGH")
    except Exception as e:
        utils.log(f"[Capture] 设置进程优先级失败: {e}")

    camera = None
    camera_started = False  # ⭐ 追踪启动状态

    try:
        # 创建 DXcam 相机
        camera = dxcam.create(output_idx=0, output_color="BGR")

        if camera is None:
            utils.log("[Capture] 错误：无法创建 DXcam 相机")
            capture_ready_event.set()  # 仍然设置事件，避免主进程永久等待
            return

        screen_width = camera.width
        screen_height = camera.height
        center_x = screen_width // 2
        center_y = screen_height // 2

        # 计算捕获区域 (left, top, right, bottom)
        # 添加边界检查
        left = max(0, center_x - crop_size // 2)
        top = max(0, center_y - crop_size // 2)
        right = min(screen_width, left + crop_size)
        bottom = min(screen_height, top + crop_size)
        region = (left, top, right, bottom)

        # 验证区域有效性
        actual_width = right - left
        actual_height = bottom - top
        if actual_width != crop_size or actual_height != crop_size:
            utils.log(
                f"[Capture] 警告：实际捕获区域 {actual_width}x{actual_height} 与请求的 {crop_size}x{crop_size} 不同")

        utils.log(f"[Capture] 捕获区域: {region}")
        utils.log(f"[Capture] 屏幕分辨率: {screen_width}x{screen_height}")

        target_fps = config_manager.get_config("CAPTURE_FPS", 120)
        utils.log(f"[Capture] 目标帧率: {target_fps} FPS")

        # 启动捕获
        camera.start(region=region, target_fps=target_fps, video_mode=True)
        camera_started = True  # ⭐ 标记已启动

        # 通知主进程捕获已就绪
        capture_ready_event.set()
        utils.log("[Capture] 捕获进程已启动")

        # 缓存函数引用（微优化）
        queue_full = frame_queue.full
        queue_put_nowait = frame_queue.put_nowait
        get_frame = camera.get_latest_frame

        # 性能统计变量
        frame_count = 0
        dropped_frames = 0
        last_stat_time = time.time()
        enable_stats = config_manager.get_config("CAPTURE_ENABLE_STATS", False)
        stats_interval = 5.0  # 每5秒统计一次

        # 空帧计数（用于检测异常）
        consecutive_empty_frames = 0
        max_empty_frames = 100  # 连续100个空帧则警告

        # ⭐ 主循环（支持优雅退出）
        while True:
            # 检查退出信号
            if stop_event is not None and stop_event.is_set():
                utils.log("[Capture] 收到停止信号，正在退出...")
                break

            # 队列满时短暂休眠
            if queue_full():
                time.sleep(0.0005)
                dropped_frames += 1
                continue

            # 获取最新帧
            frame = get_frame()

            if frame is not None:
                consecutive_empty_frames = 0
                try:
                    queue_put_nowait(frame)
                    frame_count += 1
                except Exception:
                    # 队列满，跳过此帧
                    dropped_frames += 1
            else:
                consecutive_empty_frames += 1
                if consecutive_empty_frames >= max_empty_frames:
                    utils.log(f"[Capture] 警告：连续 {consecutive_empty_frames} 帧为空")
                    consecutive_empty_frames = 0
                time.sleep(0.0005)

            # 性能统计（可选）
            if enable_stats:
                current_time = time.time()
                elapsed = current_time - last_stat_time
                if elapsed >= stats_interval:
                    actual_fps = frame_count / elapsed
                    drop_rate = (dropped_frames / (frame_count + dropped_frames) * 100) if (
                                                                                                       frame_count + dropped_frames) > 0 else 0
                    utils.log(f"[Capture] 统计: FPS={actual_fps:.1f}, 丢帧率={drop_rate:.1f}%")

                    frame_count = 0
                    dropped_frames = 0
                    last_stat_time = current_time

    except Exception as e:
        utils.log(f"[Capture] DXcam 捕获错误: {e}")
        traceback.print_exc()

        # 确保设置就绪事件，避免主进程永久等待
        if not capture_ready_event.is_set():
            capture_ready_event.set()

    finally:
        # ⭐ 安全清理
        if camera is not None:
            try:
                if camera_started:  # 只在成功启动后才调用 stop
                    camera.stop()
                    utils.log("[Capture] 相机已停止")
                del camera
            except Exception as e:
                utils.log(f"[Capture] 清理相机时出错: {e}")

        utils.log("[Capture] 捕获进程已退出")


def create_capture_process(frame_queue, crop_size):
    """
    工厂函数：创建捕获进程及相关事件

    Args:
        frame_queue: 帧队列
        crop_size: 捕获区域大小

    Returns:
        tuple: (process, ready_event, stop_event)
    """
    from multiprocessing import Process, Event

    capture_ready_event = Event()
    stop_capture_event = Event()

    capture_process = Process(
        target=capture_screen,
        args=(frame_queue, capture_ready_event, crop_size, stop_capture_event),
        name="CaptureProcess",
        daemon=True
    )

    return capture_process, capture_ready_event, stop_capture_event
