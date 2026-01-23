"""
鼠标控制器模块 - 工厂入口
"""
from config_manager import get_config
from .mouse_controller import MouseControllerBase
from .driver_mouse import DriverMouseController
from .mtkmbox_mouse import MTKMBOXMouseController
from .winapi_mouse import WinAPIMouseController
from .makcu_mouse import MakcuMouseController

import utils


def create_mouse_controller(
    use_makcu=None,
    use_mtkmbox=None,
    use_driver=None,
    shared_makcu_controller=None,     # ⭐ 重命名参数（明确含义）
    shared_mtkmbox_device=None,       # ⭐ 新增参数
    **kwargs
):
    """
    工厂函数：创建鼠标控制器实例

    优先级: MTKMBOX > Makcu > Driver > WinAPI

    Args:
        use_makcu: True=强制使用Makcu, None=读取配置
        use_mtkmbox: True=强制使用MTKMBOX, None=读取配置
        use_driver: True=驱动模式, False=WinAPI模式, None=读取配置
        shared_makcu_controller: 共享的 Makcu 控制器实例 ⭐
        shared_mtkmbox_device: 共享的 MTKmbox 设备实例 ⭐
        **kwargs: 传递给控制器的其他参数
    """

    # ========== 1. MTKMBOX 硬件（优先级最高）⭐ ==========
    if use_mtkmbox is None:
        use_mtkmbox = get_config("USE_MTKMBOX", False)

    if use_mtkmbox:
        try:
            utils.log("[MouseFactory] 尝试初始化 MTKMBOX 硬件控制器...")

            # ⭐ 检查共享设备是否有效
            if shared_mtkmbox_device and shared_mtkmbox_device.is_connected():
                utils.log("[MouseFactory] 使用共享的 MTKmbox 设备实例")
                controller = MTKMBOXMouseController(
                    shared_device=shared_mtkmbox_device,  # ⭐ 传递共享设备
                    debug=kwargs.get('debug', False)  # ⭐ 传递 debug 参数
                )
                utils.log("[MouseFactory] ✅ MTKMBOX 模式启动成功")
                return controller
            else:
                utils.log("[MouseFactory] ⚠️ 共享的 MTKmbox 设备无效或未连接")
                raise RuntimeError("MTKmbox 设备不可用")

        except Exception as e:
            utils.log(f"[MouseFactory] ⚠ MTKMBOX 初始化失败: {e}")

            # 检查是否允许降级
            auto_fallback = get_config("MOUSE_MODE_AUTO_FALLBACK", True)
            if not auto_fallback:
                raise
            utils.log("[MouseFactory] 正在自动降级到其他模式...")

    # ========== 2. Makcu 硬件 ==========
    if use_makcu is None:
        use_makcu = get_config("USE_MAKCU", False)

    if use_makcu:
        try:
            utils.log("[MouseFactory] 尝试初始化 Makcu 硬件控制器...")

            # 检查共享控制器是否有效
            if shared_makcu_controller and shared_makcu_controller.is_connected():
                utils.log("[MouseFactory] 使用共享的 Makcu 控制器实例")
                controller = MakcuMouseController(
                    shared_controller=shared_makcu_controller,  # ⭐ 传递共享控制器
                )
                utils.log("[MouseFactory] ✅ Makcu 模式启动成功")
                return controller
            else:
                utils.log("[MouseFactory] ⚠️ 共享的 Makcu 控制器无效或未连接")
                raise RuntimeError("Makcu 控制器不可用")

        except Exception as e:
            utils.log(f"[MouseFactory] ⚠ Makcu 初始化失败: {e}")

            # 检查是否允许降级
            auto_fallback = get_config("MOUSE_MODE_AUTO_FALLBACK", True)
            if not auto_fallback:
                raise
            utils.log("[MouseFactory] 正在自动降级到其他模式...")

    # ========== 3. 驱动模式 ==========
    if use_driver is None:
        use_driver = get_config("USE_DRIVER_MODE", False)

    if use_driver:
        try:
            utils.log("[MouseFactory] 尝试初始化驱动模式控制器...")
            controller = DriverMouseController(**kwargs)
            utils.log("[MouseFactory] ✅ 驱动模式控制器创建成功")
            return controller
        except Exception as e:
            utils.log(f"[MouseFactory] ⚠ 驱动模式创建失败: {e}")

            # 检查是否允许降级
            auto_fallback = get_config("MOUSE_MODE_AUTO_FALLBACK", True)
            if not auto_fallback:
                raise
            utils.log("[MouseFactory] 正在自动降级到 WinAPI 模式...")

    # ========== 4. WinAPI 模式（默认/降级）==========
    utils.log("[MouseFactory] 创建 WinAPI 模式控制器")
    return WinAPIMouseController()


__all__ = [
    'MouseControllerBase',
    'DriverMouseController',
    'WinAPIMouseController',
    'MakcuMouseController',
    'MTKMBOXMouseController',
    'create_mouse_controller',
]
