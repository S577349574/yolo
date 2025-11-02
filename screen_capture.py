import time
import numpy as np
import mss

import config_manager
import utils


def capture_screen(frame_queue, capture_ready_event, crop_size):
    """优化版截图进程"""
    try:
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

            # 🆕 目标帧率控制（例如 60 FPS）
            target_fps = config_manager.get_config("CAPTURE_FPS",60)
            frame_interval = 1.0 / target_fps
            last_capture_time = 0

            while True:
                current_time = time.time()

                # 🆕 帧率限制
                if current_time - last_capture_time < frame_interval:
                    time.sleep(0.001)
                    continue

                # 🆕 只在队列有空间时捕获
                if frame_queue.full():
                    time.sleep(frame_interval)  # 队列满时休眠更久
                    continue

                img = np.array(sct.grab(crop_area))
                frame_queue.put(img, block=False)  # 非阻塞放入
                last_capture_time = current_time

    except Exception as e:
        utils.log(f"捕获进程错误: {e}")
