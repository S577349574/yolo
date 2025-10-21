"""屏幕捕获进程"""
import time
import numpy as np
import mss

import utils


def capture_screen(frame_queue, capture_ready_event, crop_size):
    """持续捕获屏幕中心区域"""
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            center_x = monitor['width'] // 2
            center_y = monitor['height'] // 2

            crop_area = {
                'left': center_x - crop_size // 2,
                'top': center_y - crop_size // 2,
                'width': crop_size,
                'height': crop_size
            }

            utils.log(f"捕获区域: {crop_area}")
            capture_ready_event.set()

            while True:
                img = np.array(sct.grab(crop_area))
                if not frame_queue.full():
                    frame_queue.put(img)
                time.sleep(0.001)
    except Exception as e:
        utils.log(f"捕获进程错误: {e}")
