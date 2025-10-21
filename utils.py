"""工具函数"""
import math

import config_manager


def get_screen_info():
    """获取屏幕信息"""
    import mss
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        return {
            'width': monitor['width'],
            'height': monitor['height'],
            'center_x': monitor['width'] // 2,
            'center_y': monitor['height'] // 2
        }


def calculate_capture_area(crop_size):
    """计算捕获区域"""
    screen_info = get_screen_info()
    return {
        'left': screen_info['center_x'] - crop_size // 2,
        'top': screen_info['center_y'] - crop_size // 2,
        'width': crop_size,
        'height': crop_size
    }


def calculate_distance(x1, y1, x2, y2):
    """计算两点距离"""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

def log(message):
    """打印日志（仅当ENABLE_LOGGING为True时输出）"""
    if config_manager.get_config("ENABLE_LOGGING"):
        print(message)
