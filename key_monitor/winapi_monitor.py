"""WinAPI 按键监控实现"""

from typing import Dict
import win32api
import win32con
from .base import KeyMonitorBase


class WinAPIKeyMonitor(KeyMonitorBase):
    """基于 WinAPI 的按键监控"""

    def __init__(self, app_state,
                 enable_left: bool = False,
                 enable_right: bool = True,
                 enable_mouse4: bool = False,
                 enable_mouse5: bool = False,
                 enable_auto_fire: bool = False,
                 poll_interval: float = 0.05):
        """
        初始化 WinAPI 监控器

        Args:
            app_state: 应用状态对象
            enable_left: 是否监听左键（WinAPI 会监听所有，此参数仅用于日志）
            enable_right: 是否监听右键
            enable_mouse4: 是否监听侧键4
            enable_mouse5: 是否监听侧键5
            enable_auto_fire: 是否启用自动开火
            poll_interval: 轮询间隔
        """
        # ⭐ 只传递基类需要的参数
        super().__init__(app_state, poll_interval=poll_interval)

        # 保存配置（用于日志和调试）
        self.enable_left = enable_left
        self.enable_right = enable_right
        self.enable_mouse4 = enable_mouse4
        self.enable_mouse5 = enable_mouse5
        self.enable_auto_fire = enable_auto_fire

        # 虚拟键码映射
        self.vk_map = {
            'f12': win32con.VK_F12,
            'left': win32con.VK_LBUTTON,    # 0x01
            'right': win32con.VK_RBUTTON,   # 0x02
            'middle': win32con.VK_MBUTTON,  # 0x04
            'mouse4': win32con.VK_XBUTTON1, # 0x05
            'mouse5': win32con.VK_XBUTTON2, # 0x06
        }

    def _initialize(self) -> bool:
        """初始化（WinAPI 无需特殊初始化）"""
        return True

    def _cleanup(self):
        """清理（WinAPI 无需清理）"""
        pass

    def is_key_pressed(self, key: str) -> bool:
        """
        检查按键是否按下

        Args:
            key: 按键名称（'left', 'right', 'mouse4', 'mouse5', 'f12' 等）

        Returns:
            bool: 是否按下
        """
        vk = self.vk_map.get(key.lower())
        if vk is None:
            return False

        # GetAsyncKeyState 返回值：
        # - 最高位（0x8000）表示当前是否按下
        # - 最低位表示自上次调用后是否被按下过
        state = win32api.GetAsyncKeyState(vk)
        return bool(state & 0x8000)

    def get_button_states(self) -> Dict[str, bool]:
        """
        获取所有按键状态

        注意：WinAPI 监控器会监听所有按键，
        enable_* 参数仅影响业务层的回调注册

        Returns:
            Dict[str, bool]: 所有按键的状态
        """
        return {
            'left': self.is_key_pressed('left'),
            'right': self.is_key_pressed('right'),
            'middle': self.is_key_pressed('middle'),
            'mouse4': self.is_key_pressed('mouse4'),
            'mouse5': self.is_key_pressed('mouse5'),
        }
