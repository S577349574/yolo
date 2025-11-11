# utils.py
# -*- coding: utf-8 -*-

import math
import sys
import datetime


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
    """
    安全的日志输出，兼容任何控制台编码（包括 GBK）
    自动处理 emoji 和特殊字符
    """
    try:
        # 添加时间戳
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{ts}] {message}"

        # 尝试直接打印
        print(full_msg)

    except UnicodeEncodeError:
        # 控制台不支持的字符（如 emoji）用占位符替换
        try:
            encoding = sys.stdout.encoding or "utf-8"
            # 用 ? 替换无法编码的字符
            safe_msg = full_msg.encode(encoding, errors="replace").decode(encoding)
            sys.stdout.write(safe_msg + "\n")
            sys.stdout.flush()
        except Exception:
            # 极端情况：强制转 ASCII
            try:
                ascii_msg = full_msg.encode("ascii", errors="ignore").decode("ascii")
                sys.stdout.write(ascii_msg + "\n")
                sys.stdout.flush()
            except Exception:
                # 最后的兜底：至少不崩溃
                pass

