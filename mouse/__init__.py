"""
鼠标控制器模块 - 工厂入口
"""
from config_manager import get_config
from .mouse_controller import MouseControllerBase
from .driver_mouse import DriverMouseController
from .winapi_mouse import WinAPIMouseController
from .makcu_mouse import MakcuMouseController  # <--- 导入新类

import utils


def create_mouse_controller(use_makcu=None, use_driver=None, shared_controller=None, **kwargs):
    """
    工厂函数：创建鼠标控制器实例

    Args:
        use_makcu: True=强制使用Makcu, None=读取配置
        use_driver: True=驱动模式, False=WinAPI模式, None=读取配置
        shared_controller: 共享的 Makcu controller 实例（避免重复打开串口）
        **kwargs: 传递给控制器的其他参数
    """
    if use_makcu is None:
        use_makcu = get_config("USE_MAKCU", False)

    if use_makcu:
        try:
            utils.log("[MouseFactory] 尝试初始化 Makcu 硬件控制器...")

            # ⭐ 添加调试信息
            if shared_controller:
                utils.log(f"[MouseFactory] 接收到共享 controller: {shared_controller}")
            else:
                utils.log("[MouseFactory] ⚠️ 未接收到共享 controller，将创建独立实例")

            # ⭐ 传递 shared_controller
            controller = MakcuMouseController(shared_controller=shared_controller, **kwargs)

            utils.log("[MouseFactory] Makcu 模式启动成功")
            return controller
        except Exception as e:
            utils.log(f"[MouseFactory] ⚠ Makcu 初始化失败: {e}")
            utils.log("[MouseFactory] 正在自动降级到其他模式...")
            # 失败后继续向下执行
    # 2. 检查驱动模式
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
        # 3. WinAPI 模式 (兜底)
        utils.log("[MouseFactory] 创建 WinAPI 模式控制器")
        return WinAPIMouseController()


__all__ = [
    'MouseControllerBase',
    'DriverMouseController',
    'WinAPIMouseController',
    'MakcuMouseController',
    'create_mouse_controller',
]
