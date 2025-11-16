import os
import time
import mss
import numpy as np
import psutil
import config_manager
import utils


def capture_screen(frame_queue, capture_ready_event, crop_size):
    """高性能截图进程"""
    try:
        p = psutil.Process(os.getpid())
        if os.name == 'nt':
            p.nice(psutil.HIGH_PRIORITY_CLASS)

        with mss.mss() as sct:
            screen_width = sct.monitors[1]['width']
            screen_height = sct.monitors[1]['height']

            center_x = screen_width // 2
            center_y = screen_height // 2

            crop_area = {
                'left': center_x - crop_size // 2,
                'top': center_y - crop_size // 2,
                'width': crop_size,
                'height': crop_size
            }

            utils.log(f"捕获区域: {crop_area}")
            capture_ready_event.set()

            # 目标帧率控制
            target_fps = config_manager.get_config("CAPTURE_FPS", 120)  # 提高到 120
            frame_interval = 1.0 / target_fps
            next_capture_time = time.perf_counter()  # 使用高精度时钟

            # 🆕 性能统计（可选）
            frame_count = 0
            stats_start = time.perf_counter()

            while True:
                current_time = time.perf_counter()

                # 🆕 动态休眠 - 根据距离下次捕获的时间决定
                time_until_next = next_capture_time - current_time
                if time_until_next > 0.002:  # 如果还有 >2ms
                    time.sleep(time_until_next * 0.5)  # 休眠一半时间
                    continue
                elif time_until_next > 0:  # 如果还有 <2ms
                    continue  # 自旋等待（更精确）

                # 🆕 队列满时跳帧而不是休眠
                if frame_queue.full():
                    next_capture_time += frame_interval  # 跳过这一帧
                    continue

                # 截图（mss 已经很快，无需额外优化）
                img = np.array(sct.grab(crop_area))

                # 🆕 非阻塞放入，如果失败就跳过
                try:
                    frame_queue.put_nowait(img)
                except:
                    pass  # 队列满了就丢弃这一帧

                # 更新下次捕获时间
                next_capture_time += frame_interval

                # 防止时间漂移（如果系统卡顿导致严重延迟）
                if next_capture_time < current_time:
                    next_capture_time = current_time + frame_interval


    except Exception as e:
        utils.log(f"❌ 捕获进程错误: {e}")
