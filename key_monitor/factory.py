"""按键监控器工厂函数（智能适配版）"""

from typing import Optional, List
import utils
from config_manager import get_config
from .base import KeyMonitorBase
from .winapi_monitor import WinAPIKeyMonitor
from .makcu_monitor import MakcuKeyMonitor


def get_monitored_keys() -> List[str]:
    """
    获取当前配置中启用的所有按键

    Returns:
        List[str]: 启用的按键列表 ['left', 'right', 'mouse4', 'mouse5']
    """
    monitored = []

    if get_config('ENABLE_LEFT_MOUSE_MONITOR', False):
        monitored.append('left')
    if get_config('ENABLE_RIGHT_MOUSE_MONITOR', False):
        monitored.append('right')
    if get_config('ENABLE_MOUSE4_MONITOR', False):
        monitored.append('mouse4')
    if get_config('ENABLE_MOUSE5_MONITOR', False):
        monitored.append('mouse5')

    return monitored


def get_primary_trigger_key() -> Optional[str]:
    """
    获取主触发键（优先级：右键 > 左键 > 侧键4 > 侧键5）

    Returns:
        Optional[str]: 主触发键名称，如果没有启用任何按键则返回 None
    """
    if get_config('ENABLE_RIGHT_MOUSE_MONITOR', False):
        return 'right'
    elif get_config('ENABLE_LEFT_MOUSE_MONITOR', False):
        return 'left'
    elif get_config('ENABLE_MOUSE4_MONITOR', False):
        return 'mouse4'
    elif get_config('ENABLE_MOUSE5_MONITOR', False):
        return 'mouse5'
    else:
        return None


def create_key_monitor(
    app_state,
    use_makcu: bool = False,
    shared_controller=None,
    enable_left: bool = False,
    enable_right: bool = True,
    enable_mouse4: bool = False,
    enable_mouse5: bool = False,
    enable_auto_fire: bool = False,
    poll_interval: float = 0.05
) -> Optional[KeyMonitorBase]:
    """
    创建按键监控器（自动适配）

    Args:
        app_state: 应用状态对象
        use_makcu: 是否使用 Makcu 硬件
        shared_controller: 共享的 Makcu 控制器实例
        enable_left: 是否监听左键
        enable_right: 是否监听右键
        enable_mouse4: 是否监听侧键4（后退键）
        enable_mouse5: 是否监听侧键5（前进键）
        enable_auto_fire: 是否启用自动开火
        poll_interval: 轮询间隔
    """
    try:
        if use_makcu:
            utils.log("[KeyMonitor] 🎮 创建 Makcu 硬件监控器")

            use_hardware = get_config("MAKCU_USE_HARDWARE_MONITOR", True)
            fallback_pynput = get_config("MAKCU_FALLBACK_TO_PYNPUT", True)

            monitor = MakcuKeyMonitor(
                app_state,
                shared_controller=shared_controller,
                enable_left=enable_left,
                enable_right=enable_right,
                enable_mouse4=enable_mouse4,
                enable_mouse5=enable_mouse5,
                enable_auto_fire=enable_auto_fire,
                poll_interval=poll_interval,
                use_hardware_monitor=use_hardware,
                fallback_to_pynput=fallback_pynput
            )
        else:
            utils.log("[KeyMonitor] 🖱️ 创建 WinAPI 系统监控器")
            monitor = WinAPIKeyMonitor(
                app_state,
                enable_left=enable_left,
                enable_right=enable_right,
                enable_mouse4=enable_mouse4,
                enable_mouse5=enable_mouse5,
                enable_auto_fire=enable_auto_fire,
                poll_interval=poll_interval
            )

        # ⭐ 使用新方法显示配置
        monitored_keys = get_monitored_keys()
        utils.log(f"[KeyMonitor] 配置:")
        utils.log(f"  - 监听左键: {enable_left}")
        utils.log(f"  - 监听右键: {enable_right}")
        utils.log(f"  - 监听侧键4: {enable_mouse4}")
        utils.log(f"  - 监听侧键5: {enable_mouse5}")
        utils.log(f"  - 自动开火: {enable_auto_fire}")

        if monitored_keys:
            key_names = {
                'left': '左键', 'right': '右键',
                'mouse4': '侧键4', 'mouse5': '侧键5'
            }
            utils.log(f"  - 已启用按键: {[key_names[k] for k in monitored_keys]}")

        if use_makcu:
            utils.log(f"  - 硬件监视: {use_hardware}")
            utils.log(f"  - Pynput回退: {fallback_pynput}")
            utils.log(f"  - 共享模式: {shared_controller is not None}")

        return monitor

    except Exception as e:
        utils.log(f"[KeyMonitor] ❌ 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return None
