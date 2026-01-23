"""基于 MTKmbox 硬件的鼠标控制器"""

from typing import Optional
import time
import utils
from config_manager import get_config
from .serial_base import SerialMouseControllerBase


class MTKMBOXMouseController(SerialMouseControllerBase):
    """MTKmbox 硬件鼠标控制器"""

    def __init__(
            self,
            shared_device=None,
            app_state=None,
            debug: bool = False
    ):
        """
        初始化 MTKmbox 鼠标控制器

        Args:
            shared_device: 共享的 MTKMBOX 设备实例
            app_state: 应用状态对象
            debug: 是否启用调试模式
        """
        self.debug = debug
        self._log_prefix = "[MTKMBOX]"

        # ⭐ 关键修复：将 shared_device 传递给父类
        super().__init__(shared_controller=shared_device)

    # ==================== 实现抽象方法 ====================

    def get_mode(self) -> str:
        """返回控制器模式"""
        return "MTKMBOX"

    def _connect_device(self):
        """
        连接 MTKmbox 设备（仅在独立模式下调用）

        ⚠️ 如果使用共享设备，此方法不应该被调用
        """
        # ⭐ 添加检查：如果是共享模式，不应该执行这里
        if self._is_shared:
            self._log("⚠️ 共享模式下不应调用 _connect_device()")
            return

        try:
            from mtkmbox import MTKMBOX

            port = get_config("MTKMBOX_PORT", "COM6")
            vid = get_config("MTKMBOX_VID", 0x0416)
            pid = get_config("MTKMBOX_PID", 0x5020)

            self.controller = MTKMBOX(
                port=port,
                vid=vid,
                pid=pid,
                debug=self.debug
            )
            time.sleep(0.3)

            if not self.controller.is_connected():
                raise RuntimeError("MTKmbox 设备连接失败")

            self._log("✅ MTKmbox 设备连接成功")

        except Exception as e:
            self._log(f"❌ MTKmbox 设备初始化失败: {e}")
            raise

    def _hardware_move(self, dx: int, dy: int):
        """发送移动指令到 MTKmbox 硬件"""
        if not self.controller:
            raise RuntimeError("MTKmbox 设备未初始化")

        max_move = get_config("MTKMBOX_MAX_MOVE", 127)

        # 分段大幅移动
        while dx != 0 or dy != 0:
            step_dx = max(-max_move, min(max_move, dx))
            step_dy = max(-max_move, min(max_move, dy))

            self.controller.move(step_dx, step_dy)

            dx -= step_dx
            dy -= step_dy

    def _hardware_button(self, button_flags: int):
        """发送按键指令到 MTKmbox 硬件"""
        if not self.controller:
            raise RuntimeError("MTKmbox 设备未初始化")

        # MTKmbox 的按键映射
        button_map = {
            0x01: 'left',
            0x02: 'right',
            0x04: 'middle'
        }

        for flag, button_name in button_map.items():
            if button_flags & flag:
                self.controller.click(button_name, press=True)
            else:
                self.controller.click(button_name, press=False)

    def _disconnect_device(self):
        """断开 MTKmbox 设备连接"""
        if self.controller and not self._is_shared:
            try:
                self.controller.close()
                self._log("✅ MTKmbox 设备已断开")
            except Exception as e:
                self._log(f"⚠️ 断开设备时出错: {e}")

    # ==================== 辅助方法 ====================

    def is_connected(self) -> bool:
        """检查设备连接状态"""
        return bool(self.controller and self.controller.is_connected())

    def _log(self, msg: str):
        """统一日志输出"""
        if self.debug or "❌" in msg or "⚠️" in msg:
            utils.log(f"{self._log_prefix} {msg}")
