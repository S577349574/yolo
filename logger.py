"""
统一日志系统（完全独立，无外部依赖）
配置通过外部主动设置，而不是内部读取
"""
import sys
import datetime
from typing import Literal

# ========== 内部状态（仅通过 setter 修改）==========
_LOGGING_ENABLED = True  # 默认开启
_LOG_LEVEL = 'INFO'      # 默认级别

LogLevel = Literal['DEBUG', 'INFO', 'WARNING', 'ERROR']

_LEVEL_PRIORITY = {
    'DEBUG': 0,
    'INFO': 1,
    'WARNING': 2,
    'ERROR': 3
}


# ========== 配置接口（由外部模块调用）==========
def set_logging_enabled(enabled: bool):
    """设置日志开关（由 config_manager 调用）"""
    global _LOGGING_ENABLED
    _LOGGING_ENABLED = enabled


def set_log_level(level: LogLevel):
    """设置日志级别（由 config_manager 调用）"""
    global _LOG_LEVEL
    _LOG_LEVEL = level.upper()


def get_logging_enabled() -> bool:
    """获取当前日志开关状态"""
    return _LOGGING_ENABLED


def get_log_level() -> str:
    """获取当前日志级别"""
    return _LOG_LEVEL


# ========== 核心日志函数 ==========
def log(message: str, level: LogLevel = 'INFO'):
    """
    统一日志输出函数

    Args:
        message: 日志内容
        level: 日志级别 ('DEBUG', 'INFO', 'WARNING', 'ERROR')
    """
    # 检查是否启用
    if not _LOGGING_ENABLED:
        return

    # 日志级别过滤
    if _LEVEL_PRIORITY.get(level, 1) < _LEVEL_PRIORITY.get(_LOG_LEVEL, 1):
        return

    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{ts}] [{level}] {message}"
        print(full_msg, flush=True)
    except UnicodeEncodeError:
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
                pass


# ========== 便捷函数 ==========
def log_debug(message: str):
    """调试日志"""
    log(message, level='DEBUG')


def log_info(message: str):
    """信息日志"""
    log(message, level='INFO')


def log_warning(message: str):
    """警告日志"""
    log(message, level='WARNING')


def log_error(message: str):
    """错误日志"""
    log(message, level='ERROR')
