"""键盘控制器工厂函数"""

from typing import Optional
import utils
from .base import KeyboardControllerBase
from .winapi_keyboard import WinAPIKeyboardController
from .makcu_keyboard import MakcuKeyboardController


def create_keyboard_controller(
    use_makcu: bool = False,
    shared_controller=None,
    debug_mode: bool = False
) -> Optional[KeyboardControllerBase]:
    """
    创建键盘控制器

    Args:
        use_makcu: 是否使用 Makcu 硬件模式
        shared_controller: 共享的 Makcu controller（用于共享模式）
        debug_mode: 调试模式

    Returns:
        KeyboardControllerBase: 键盘控制器实例，失败返回 None
    """
    try:
        if use_makcu:
            utils.log("[KeyboardFactory] 🎮 创建 Makcu 硬件键盘控制器")
            controller = MakcuKeyboardController(
                shared_controller=shared_controller,
                debug_mode=debug_mode
            )
        else:
            utils.log("[KeyboardFactory] 🖱️ 创建 WinAPI 键盘控制器")
            controller = WinAPIKeyboardController(debug_mode=debug_mode)

        # 显示配置摘要
        utils.log(f"[KeyboardFactory] 配置:")
        utils.log(f"  - 控制模式: {controller.get_mode()}")
        utils.log(f"  - 调试模式: {debug_mode}")

        if use_makcu:
            utils.log(f"  - 共享模式: {shared_controller is not None}")

        return controller

    except Exception as e:
        utils.log(f"[KeyboardFactory] ❌ 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return None
