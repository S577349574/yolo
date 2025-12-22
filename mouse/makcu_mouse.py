"""
Makcu 硬件模式鼠标控制器
基于 Makcu v2.3.0 API 适配
"""
import time
import utils
from config_manager import get_config
from .mouse_controller import MouseControllerBase

# 尝试导入 makcu 库
try:
    from makcu import create_controller, MouseButton
    MAKCU_AVAILABLE = True
except ImportError:
    MAKCU_AVAILABLE = False
    create_controller = None
    MouseButton = None


class MakcuMouseController(MouseControllerBase):
    """Makcu 硬件鼠标控制器"""

    def __init__(self, shared_controller=None):
        """
        初始化 Makcu 控制器

        Args:
            shared_controller: 外部传入的 Makcu controller 实例（避免重复连接）
        """
        if not MAKCU_AVAILABLE:
            raise RuntimeError("未安装 makcu 库。请运行: pip install makcu")

        super().__init__()

        # ⭐ 优先使用共享的 controller
        if shared_controller is not None:
            utils.log("[MakcuMouse] 使用共享的 Makcu controller 实例")
            self.controller = shared_controller
            self._is_shared = True  # 标记为共享模式，析构时不关闭
        else:
            utils.log("[MakcuMouse] 创建独立的 Makcu controller 实例")
            self.controller = None
            self._is_shared = False
            self._connect_device()
        self.btn_map = {
            self.BUTTON_LEFT_DOWN:   (MouseButton.LEFT, 'press'),
            self.BUTTON_LEFT_UP:     (MouseButton.LEFT, 'release'),
            self.BUTTON_RIGHT_DOWN:  (MouseButton.RIGHT, 'press'),
            self.BUTTON_RIGHT_UP:    (MouseButton.RIGHT, 'release'),
            self.BUTTON_MIDDLE_DOWN: (MouseButton.MIDDLE, 'press'),
            self.BUTTON_MIDDLE_UP:   (MouseButton.MIDDLE, 'release'),
        }

        # 启动工作线程 (PID循环)
        self._start_worker_thread()

        utils.log("[MakcuMouse] 初始化完成，硬件已就绪")

    def _connect_device(self):
        """连接 Makcu 硬件"""
        try:
            # 读取新配置
            port = get_config("MAKCU_PORT", "")
            auto_reconnect = get_config("MAKCU_AUTO_RECONNECT", True)

            # 如果配置里填了端口，就传给 fallback_com_port 或 override_port
            # create_controller 参数: (fallback_com_port='', debug=False, send_init=True, auto_reconnect=True)
            self.controller = create_controller(
                fallback_com_port=port,
                debug=self.debug_mode,
                auto_reconnect=auto_reconnect
            )

            # 等待一小会儿确保握手完成
            time.sleep(0.5)

            if not self.controller.is_connected():
                utils.log("[MakcuMouse] 警告: 控制器对象已创建但硬件未连接")
            else:
                info = self.controller.get_device_info()
                utils.log(f"[MakcuMouse] 设备已连接: {info.get('version', 'Unknown Ver')}")

        except Exception as e:
            utils.log(f"[MakcuMouse] 设备连接初始化失败: {e}")
            raise RuntimeError(f"Makcu 连接失败: {e}")

    # ==================== 实现抽象方法 ====================

    def get_mode(self) -> str:
        return "Makcu"

    def is_ready(self) -> bool:
        """检查控制器状态"""
        return (
            self.controller is not None and
            self.controller.is_connected() and
            self._is_initialized and
            self.mouse_thread is not None and
            self.mouse_thread.is_alive()
        )

    def _send_move(self, dx: int, dy: int) -> bool:
        """发送相对移动指令"""
        if not self.controller:
            return False

        try:
            # API: move(dx: int, dy: int) -> None
            self.controller.move(int(dx), int(dy))
            return True
        except Exception as e:
            # 只有在 debug 模式下才频繁打印移动错误，避免刷屏
            if self.debug_mode:
                utils.log(f"[MakcuMouse] 移动失败: {e}")
            return False

    def _send_button(self, button_flags: int) -> bool:
        """发送按键指令 (按下或抬起)"""
        if not self.controller:
            return False

        mapping = self.btn_map.get(button_flags)
        if not mapping:
            utils.log(f"[MakcuMouse] 未知按键标志: {button_flags}")
            return False

        btn_enum, action = mapping

        try:
            # 根据 API 文档使用 press 和 release
            if action == 'press':
                self.controller.press(btn_enum)
            elif action == 'release':
                self.controller.release(btn_enum)

            return True
        except Exception as e:
            utils.log(f"[MakcuMouse] 按键操作失败 ({action}): {e}")
            return False

    def _do_close(self):
        """清理资源"""
        if self.controller:
            # ⭐ 只有非共享模式才断开连接
            if not self._is_shared:
                try:
                    utils.log("[MakcuMouse] 断开设备连接...")
                    self.controller.disconnect()
                except Exception as e:
                    utils.log(f"[MakcuMouse] 断开连接时出错: {e}")
            else:
                utils.log("[MakcuMouse] 共享模式，跳过断开连接")

            self.controller = None