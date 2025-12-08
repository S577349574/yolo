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

            target_fps = config_manager.get_config("CAPTURE_FPS", 120)  # 提高到 120
            frame_interval = 1.0 / target_fps
            next_capture_time = time.perf_counter()

            while True:
                current_time = time.perf_counter()

                time_until_next = next_capture_time - current_time
                if time_until_next > 0.002:
                    time.sleep(time_until_next * 0.5)
                    continue
                elif time_until_next > 0:
                    continue

                if frame_queue.full():
                    next_capture_time += frame_interval
                    continue

                img = np.array(sct.grab(crop_area))

                try:
                    frame_queue.put_nowait(img)
                except:
                    pass

                next_capture_time += frame_interval

                if next_capture_time < current_time:
                    next_capture_time = current_time + frame_interval


    except Exception as e:
        utils.log(f"捕获进程错误: {e}")
