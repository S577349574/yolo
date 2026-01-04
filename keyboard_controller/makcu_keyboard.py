"""
Makcu 硬件键盘控制器
基于 Makcu API 适配
"""

import time
import utils
from config_manager import get_config
from makcu import create_controller

from keyboard_controller import KeyboardControllerBase


class MakcuKeyboardController(KeyboardControllerBase):
    """Makcu 硬件键盘控制器"""

    def __init__(self, shared_controller=None, debug_mode: bool = False):
        """
        初始化 Makcu 键盘控制器

        Args:
            shared_controller: 外部传入的 Makcu controller（避免重复连接）
            debug_mode: 调试模式
        """
        super().__init__(debug_mode)

        # ⭐ 优先使用共享的 controller
        if shared_controller is not None:
            utils.log("[MakcuKeyboard] 使用共享的 Makcu controller 实例")
            self.controller = shared_controller
            self._is_shared = True
        else:
            utils.log("[MakcuKeyboard] 创建独立的 Makcu controller 实例")
            self.controller = None
            self._is_shared = False

    # ==================== 实现抽象方法 ====================

    def get_mode(self) -> str:
        return "Makcu"

    def is_ready(self) -> bool:
        return (
            self.controller is not None and
            self.controller.is_connected() and
            self._is_initialized
        )

    def _do_initialize(self) -> bool:
        """初始化 Makcu 控制器"""
        # 如果是共享模式，直接返回成功
        if self._is_shared and self.controller:
            return True

        # 独立模式：连接设备
        try:
            port = get_config("MAKCU_PORT", "")
            auto_reconnect = get_config("MAKCU_AUTO_RECONNECT", True)

            self.controller = create_controller(
                fallback_com_port=port,
                debug=self.debug_mode,
                auto_reconnect=auto_reconnect
            )

            time.sleep(0.5)  # 等待握手完成

            if not self.controller.is_connected():
                utils.log("[MakcuKeyboard] 警告: 控制器对象已创建但硬件未连接")
                return False

            info = self.controller.get_device_info()
            utils.log(f"[MakcuKeyboard] 设备已连接: {info.get('version', 'Unknown')}")
            return True

        except Exception as e:
            utils.log(f"[MakcuKeyboard] 设备连接失败: {e}")
            return False

    def _do_close(self):
        """清理资源"""
        if self.controller:
            # ⭐ 只有非共享模式才断开连接
            if not self._is_shared:
                try:
                    utils.log("[MakcuKeyboard] 断开设备连接...")
                    self.controller.disconnect()
                except Exception as e:
                    utils.log(f"[MakcuKeyboard] 断开连接失败: {e}")
            else:
                utils.log("[MakcuKeyboard] 共享模式，跳过断开连接")

            self.controller = None

    def _send_key_down(self, key: str) -> bool:
        """按下按键"""
        if not self.controller or not self.controller.is_connected():
            return False

        try:
            cmd = f".down('{key}')\r\n"
            self.controller._send_command(cmd)
            return True
        except Exception as e:
            if self.debug_mode:
                utils.log(f"[MakcuKeyboard] 按下失败 ({key}): {e}")
            return False

    def _send_key_up(self, key: str) -> bool:
        """释放按键"""
        if not self.controller or not self.controller.is_connected():
            return False

        try:
            cmd = f".up('{key}')\r\n"
            self.controller._send_command(cmd)
            return True
        except Exception as e:
            if self.debug_mode:
                utils.log(f"[MakcuKeyboard] 释放失败 ({key}): {e}")
            return False

    def _send_key_press(self, key: str, hold_ms: int = 0, rand_ms: int = 0) -> bool:
        """按下并释放按键"""
        if not self.controller or not self.controller.is_connected():
            return False

        try:
            if hold_ms > 0:
                cmd = f".press('{key}',{hold_ms},{rand_ms})\r\n"
            else:
                cmd = f".press('{key}')\r\n"

            self.controller._send_command(cmd)
            return True
        except Exception as e:
            if self.debug_mode:
                utils.log(f"[MakcuKeyboard] 按键失败 ({key}): {e}")
            return False

    def _send_string(self, text: str) -> bool:
        """输入字符串"""
        if not self.controller or not self.controller.is_connected():
            return False

        try:
            # 转义双引号
            text_escaped = text.replace('"', '\\"')
            cmd = f'.string("{text_escaped}")\r\n'
            self.controller._send_command(cmd)
            return True
        except Exception as e:
            utils.log(f"[MakcuKeyboard] 输入字符串失败: {e}")
            return False

    def _is_key_down(self, key: str) -> bool:
        """查询按键是否按下"""
        if not self.controller or not self.controller.is_connected():
            return False

        try:
            cmd = f".isdown('{key}')\r\n"
            response = self.controller._send_command(cmd)
            # 解析响应（示例: "km.isdown(1)\r\n>>>"）
            if response and "isdown(1)" in response:
                return True
            return False
        except Exception as e:
            if self.debug_mode:
                utils.log(f"[MakcuKeyboard] 查询失败 ({key}): {e}")
            return False

    def reset(self) -> bool:
        """清除键盘状态（使用 Makcu 的 init 命令）"""
        if not self.controller or not self.controller.is_connected():
            return False

        try:
            self.controller._send_command(".init()\r\n")
            utils.log("[MakcuKeyboard] 键盘状态已重置")
            return True
        except Exception as e:
            utils.log(f"[MakcuKeyboard] 重置失败: {e}")
            return False
