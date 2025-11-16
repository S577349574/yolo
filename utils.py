# utils.py
# -*- coding: utf-8 -*-

import math
import sys
import datetime
from config_manager import get_config  # ← 添加这一行

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


_LOGGING_ENABLED = None
_LOG_LEVEL = None


def _init_logging_config():
    """初始化日志配置（只在首次调用时执行）"""
    global _LOGGING_ENABLED, _LOG_LEVEL
    if _LOGGING_ENABLED is None:
        _LOGGING_ENABLED = get_config('ENABLE_LOGGING', True)  # 默认开启
        _LOG_LEVEL = get_config('LOG_LEVEL', 'INFO')  # INFO/DEBUG/WARNING/ERROR


def log(message, level='INFO'):
    """
    安全的日志输出（带配置控制）

    Args:
        message: 日志内容
        level: 日志级别 ('DEBUG', 'INFO', 'WARNING', 'ERROR')
    """
    # 首次调用时初始化配置
    _init_logging_config()

    # 🆕 检查是否启用日志
    if not _LOGGING_ENABLED:
        return  # ← 零开销退出

    # 🆕 日志级别过滤
    level_priority = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3}
    if level_priority.get(level, 1) < level_priority.get(_LOG_LEVEL, 1):
        return

    try:
        # 添加时间戳和日志级别
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{ts}] [{level}] {message}"

        # 尝试直接打印
        print(full_msg, flush=True)

    except UnicodeEncodeError:
        # 控制台不支持的字符（如 emoji）用占位符替换
        try:
            encoding = sys.stdout.encoding or "utf-8"
            safe_msg = full_msg.encode(encoding, errors="replace").decode(encoding)
            sys.stdout.write(safe_msg + "\n")
            sys.stdout.flush()
        except Exception:
            try:
                ascii_msg = full_msg.encode("ascii", errors="ignore").decode("ascii")
                sys.stdout.write(ascii_msg + "\n")
                sys.stdout.flush()
            except Exception:
                pass  # 最后的兜底


# 🆕 便捷函数（可选）
def log_debug(message):
    """调试日志（只在 LOG_LEVEL=DEBUG 时输出）"""
    log(message, level='DEBUG')


def log_info(message):
    """信息日志"""
    log(message, level='INFO')


def log_warning(message):
    """警告日志"""
    log(message, level='WARNING')


def log_error(message):
    """错误日志（总是输出）"""
    log(message, level='ERROR')