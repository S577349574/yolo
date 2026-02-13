"""按键监控器工厂函数（全键监控适配版）"""

from typing import Optional, List
import utils
from config.config_manager import get_config
from .base import KeyMonitorBase
from .winapi_monitor import WinAPIKeyMonitor
from .makcu_monitor import MakcuKeyMonitor
from .mtkmbox_monitor import MTKmboxKeyMonitor

def get_monitored_keys() -> List[str]:
    """
    新方案：获取用户在 KEY_PROFILE_BINDINGS 中配置为 trigger=true 的按键。
    用于判断哪些键按下时应该触发『自动开火』或『压枪』等逻辑。
    """
    bindings = get_config("KEY_PROFILE_BINDINGS", {}) or {}
    monitored: List[str] = []

    if not isinstance(bindings, dict):
        return monitored

    for key in ["left", "right", "mouse4", "mouse5"]:
        v = bindings.get(key)
        if isinstance(v, dict) and bool(v.get("trigger", False)):
            monitored.append(key)

    return monitored


def get_primary_trigger_key() -> Optional[str]:
    """新方案：从 KEY_PROFILE_BINDINGS(trigger=true) 中按 KEY_PROFILE_PRIORITY 选主触发键"""
    bindings = get_config("KEY_PROFILE_BINDINGS", {}) or {}
    if not isinstance(bindings, dict):
        return None

    trigger_keys = {k for k, v in bindings.items()
                    if k in ("left", "right", "mouse4", "mouse5")
                    and isinstance(v, dict)
                    and bool(v.get("trigger", False))}

    priority = get_config("KEY_PROFILE_PRIORITY", ["left","right", "mouse5", "mouse4"]) or []
    for k in priority:
        if k in trigger_keys:
            return k

    return next(iter(trigger_keys), None)


def create_key_monitor(
        app_state,
        use_makcu: bool = False,
        use_mtkmbox: bool = False,
        shared_controller=None,
        shared_serial=None,
        enable_auto_fire: bool = False,
        poll_interval: float = 0.05,
        # 这里的参数虽然保留，但在内部会被强制设为 True
        **kwargs
) -> Optional[KeyMonitorBase]:
    """创建按键监控器（强制开启全物理按键监控）"""

    try:
        use_hardware = get_config("HARDWARE_MONITOR_PRIORITY", True)
        fallback_pynput = get_config("FALLBACK_TO_PYNPUT", True)

        # ⭐ 核心修改：强制开启所有物理按键的监听
        # 无论 config 里怎么写，底层驱动/API 都会捕获这些键的状态
        full_monitor_params = {
            "enable_left": True,
            "enable_right": True,
            "enable_mouse4": True,
            "enable_mouse5": True,
            "enable_auto_fire": enable_auto_fire
        }

        # 1. MTKmbox 硬件
        if use_mtkmbox:
            utils.log("[KeyMonitor] 创建 MTKmbox 硬件监控器 (全键监控模式)")
            monitor = MTKmboxKeyMonitor(
                app_state,
                shared_serial=shared_serial,
                use_hardware_monitor=use_hardware,
                fallback_to_pynput=fallback_pynput,
                **full_monitor_params
            )

        # 2. Makcu 硬件
        elif use_makcu:
            utils.log("[KeyMonitor] 创建 Makcu 硬件监控器 (全键监控模式)")
            monitor = MakcuKeyMonitor(
                app_state,
                shared_controller=shared_controller,
                use_hardware_monitor=use_hardware,
                fallback_to_pynput=fallback_pynput,
                **full_monitor_params
            )

        # 3. WinAPI
        else:
            utils.log("[KeyMonitor] 创建 WinAPI 系统监控器 (全键监控模式)")
            monitor = WinAPIKeyMonitor(
                app_state,
                **full_monitor_params
            )

        # 日志输出：区分“物理监听”与“逻辑触发”
        configured = get_monitored_keys()
        utils.log(f"[KeyMonitor] 状态:")
        utils.log(f"  - 物理层: 已强制开启 [左键, 右键, 侧键4, 侧键5] 的状态捕获")
        utils.log(f"  - 逻辑层 (配置触发): {configured if configured else '未配置触发键'}")
        utils.log(f"  - 自动开火功能: {'开启' if enable_auto_fire else '关闭'}")

        return monitor

    except Exception as e:
        utils.log(f"[KeyMonitor] 创建失败: {e}")
        return None