"""WinAPI 按键监控实现"""

from typing import Dict
import win32api
import win32con
from .base import KeyMonitorBase


class WinAPIKeyMonitor(KeyMonitorBase):
    """基于 WinAPI 的按键监控"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 虚拟键码映射
        self.vk_map = {
            'f12': win32con.VK_F12,
            'left': 0x01,
            'right': 0x02,
            'middle': 0x04,
            'mouse4': 0x05,
            'mouse5': 0x06,
        }

    def _initialize(self) -> bool:
        """初始化（WinAPI 无需特殊初始化）"""
        return True

    def _cleanup(self):
        """清理（WinAPI 无需清理）"""
        pass

    def is_key_pressed(self, key: str) -> bool:
        """检查按键是否按下"""
        vk = self.vk_map.get(key.lower())
        if vk is None:
            return False
        return bool(win32api.GetAsyncKeyState(vk) & 0x8000)

    def get_button_states(self) -> Dict[str, bool]:
        """获取所有按键状态"""
        return {
            'left': self.is_key_pressed('left'),
            'right': self.is_key_pressed('right'),
            'middle': self.is_key_pressed('middle'),
            'mouse4': self.is_key_pressed('mouse4'),
            'mouse5': self.is_key_pressed('mouse5'),
        }
