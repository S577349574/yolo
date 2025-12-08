"""
鼠标控制器模块

使用方式:
    from mouse import create_mouse_controller, DriverMouseController, WinAPIMouseController

    # 自动选择模式
    controller = create_mouse_controller()

    # 指定模式
    controller = create_mouse_controller(use_driver=True)
    controller = create_mouse_controller(use_driver=False)
"""
from config_manager import get_config
from .mouse_controller import MouseControllerBase
from .driver_mouse import DriverMouseController
from .winapi_mouse import WinAPIMouseController

import utils


def create_mouse_controller(use_driver=None, **kwargs):
    """
    工厂函数：创建鼠标控制器实例

    Args:
        use_driver: True=驱动模式, False=WinAPI模式, None=从配置读取
        **kwargs: 传递给控制器的其他参数

    Returns:
        MouseControllerBase: 鼠标控制器实例
    """
    if use_driver is None:
        use_driver = get_config("USE_DRIVER_MODE", True)

    if use_driver:
        try:
            controller = DriverMouseController(**kwargs)
            utils.log("[MouseFactory] 创建驱动模式控制器成功")
            return controller
        except Exception as e:
            utils.log(f"[MouseFactory] 驱动模式创建失败: {e}")
            utils.log("[MouseFactory] 自动降级到 WinAPI 模式")
            return WinAPIMouseController()
    else:
        utils.log("[MouseFactory] 创建 WinAPI 模式控制器")
        return WinAPIMouseController()


__all__ = [
    'MouseControllerBase',
    'DriverMouseController',
    'WinAPIMouseController',
    'create_mouse_controller',
]
