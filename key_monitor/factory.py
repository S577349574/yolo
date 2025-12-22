"""按键监控器工厂函数（智能适配版）"""

from typing import Optional
import utils
from config_manager import get_config
from .base import KeyMonitorBase
from .winapi_monitor import WinAPIKeyMonitor
from .makcu_monitor import MakcuKeyMonitor


def create_key_monitor(
    app_state,
    use_makcu: bool = False,
    shared_controller=None,  # ⭐ 共享控制器
    enable_left: bool = False,
    enable_right: bool = True,
    enable_auto_fire: bool = False,
    poll_interval: float = 0.05
) -> Optional[KeyMonitorBase]:
    """
    创建按键监控器（自动适配）
    """
    try:
        if use_makcu:
            utils.log("[KeyMonitor] 🎮 创建 Makcu 硬件监控器")

            # 读取 Makcu 特殊配置
            use_hardware = get_config("MAKCU_USE_HARDWARE_MONITOR", True)
            fallback_pynput = get_config("MAKCU_FALLBACK_TO_PYNPUT", True)

            monitor = MakcuKeyMonitor(
                app_state,  # ⭐ 直接传递位置参数
                shared_controller=shared_controller,
                enable_left=enable_left,         # ⭐ 关键字参数
                enable_right=enable_right,
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
                enable_auto_fire=enable_auto_fire,
                poll_interval=poll_interval
            )

        # 显示配置摘要
        utils.log(f"[KeyMonitor] 配置:")
        utils.log(f"  - 监听左键: {enable_left}")
        utils.log(f"  - 监听右键: {enable_right}")
        utils.log(f"  - 自动开火: {enable_auto_fire}")

        if use_makcu:
            utils.log(f"  - 硬件监视: {use_hardware}")
            utils.log(f"  - Pynput回退: {fallback_pynput}")
            utils.log(f"  - 共享模式: {shared_controller is not None}")  # ⭐ 添加调试信息

        return monitor

    except Exception as e:
        utils.log(f"[KeyMonitor] ❌ 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return None
