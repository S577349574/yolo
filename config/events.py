"""全局控制事件"""

import threading
from typing import Tuple


# ========== 控制事件定义 ==========

_resume_event = threading.Event()   # 恢复运行事件
_reload_event = threading.Event()   # 重载配置事件
_stop_event = threading.Event()     # 停止程序事件


def get_events() -> Tuple[threading.Event, threading.Event, threading.Event]:
    """
    获取所有控制事件

    Returns:
        (resume_event, reload_event, stop_event)
    """
    return _resume_event, _reload_event, _stop_event


# ========== 恢复运行事件 ==========

def signal_resume() -> None:
    """触发恢复运行事件"""
    _resume_event.set()


def wait_resume(timeout: float = None) -> bool:
    """
    等待恢复运行事件

    Args:
        timeout: 超时时间（秒），None 表示无限等待

    Returns:
        是否在超时前触发
    """
    return _resume_event.wait(timeout)


def clear_resume() -> None:
    """清除恢复运行事件"""
    _resume_event.clear()


def is_resume_set() -> bool:
    """检查恢复运行事件是否已触发"""
    return _resume_event.is_set()


# ========== 重载配置事件 ==========

def signal_reload() -> None:
    """触发重载配置事件"""
    _reload_event.set()


def wait_reload(timeout: float = None) -> bool:
    """
    等待重载配置事件

    Args:
        timeout: 超时时间（秒），None 表示无限等待

    Returns:
        是否在超时前触发
    """
    return _reload_event.wait(timeout)


def clear_reload() -> None:
    """清除重载配置事件"""
    _reload_event.clear()


def is_reload_set() -> bool:
    """检查重载配置事件是否已触发"""
    return _reload_event.is_set()


# ========== 停止程序事件 ==========

def signal_stop() -> None:
    """触发停止程序事件"""
    _stop_event.set()


def wait_stop(timeout: float = None) -> bool:
    """
    等待停止程序事件

    Args:
        timeout: 超时时间（秒），None 表示无限等待

    Returns:
        是否在超时前触发
    """
    return _stop_event.wait(timeout)


def clear_stop() -> None:
    """清除停止程序事件"""
    _stop_event.clear()


def is_stop_set() -> bool:
    """检查停止程序事件是否已触发"""
    return _stop_event.is_set()


# ========== 批量操作 ==========

def clear_all_events() -> None:
    """清除所有控制事件"""
    _resume_event.clear()
    _reload_event.clear()
    _stop_event.clear()


def get_events_status() -> dict:
    """
    获取所有事件的状态

    Returns:
        事件状态字典
    """
    return {
        "resume": _resume_event.is_set(),
        "reload": _reload_event.is_set(),
        "stop": _stop_event.is_set()
    }


def wait_any_event(timeout: float = None) -> str:
    """
    等待任意事件触发

    Args:
        timeout: 超时时间（秒），None 表示无限等待

    Returns:
        触发的事件名称（"resume"/"reload"/"stop"），超时返回 None
    """
    events = {
        "resume": _resume_event,
        "reload": _reload_event,
        "stop": _stop_event
    }

    # 轮询检查（简单实现）
    import time
    start_time = time.time()
    poll_interval = 0.01  # 10ms 轮询间隔

    while True:
        for name, event in events.items():
            if event.is_set():
                return name

        if timeout is not None and (time.time() - start_time) >= timeout:
            return None

        time.sleep(poll_interval)
