"""
WinAPI 键盘控制器
基于 Windows API 的键盘控制
"""

import time
import win32api
import win32con
from .base import KeyboardControllerBase


class WinAPIKeyboardController(KeyboardControllerBase):
    """WinAPI 键盘控制器"""

    # 虚拟键码映射表
    VK_MAP = {
        # 字母（A-Z）
        'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
        'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
        'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
        'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
        'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59,
        'z': 0x5A,

        # 数字（0-9）
        '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
        '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,

        # 功能键（F1-F12）
        'f1': win32con.VK_F1, 'f2': win32con.VK_F2, 'f3': win32con.VK_F3,
        'f4': win32con.VK_F4, 'f5': win32con.VK_F5, 'f6': win32con.VK_F6,
        'f7': win32con.VK_F7, 'f8': win32con.VK_F8, 'f9': win32con.VK_F9,
        'f10': win32con.VK_F10, 'f11': win32con.VK_F11, 'f12': win32con.VK_F12,

        # 修饰键
        'ctrl': win32con.VK_CONTROL,
        'shift': win32con.VK_SHIFT,
        'alt': win32con.VK_MENU,
        'win': win32con.VK_LWIN,
        'lctrl': win32con.VK_LCONTROL,
        'rctrl': win32con.VK_RCONTROL,
        'lshift': win32con.VK_LSHIFT,
        'rshift': win32con.VK_RSHIFT,
        'lalt': win32con.VK_LMENU,
        'ralt': win32con.VK_RMENU,
        'lwin': win32con.VK_LWIN,
        'rwin': win32con.VK_RWIN,

        # 特殊键
        'enter': win32con.VK_RETURN,
        'return': win32con.VK_RETURN,
        'space': win32con.VK_SPACE,
        'spacebar': win32con.VK_SPACE,
        'tab': win32con.VK_TAB,
        'backspace': win32con.VK_BACK,
        'back': win32con.VK_BACK,
        'delete': win32con.VK_DELETE,
        'del': win32con.VK_DELETE,
        'escape': win32con.VK_ESCAPE,
        'esc': win32con.VK_ESCAPE,

        # 导航键
        'up': win32con.VK_UP,
        'down': win32con.VK_DOWN,
        'left': win32con.VK_LEFT,
        'right': win32con.VK_RIGHT,
        'home': win32con.VK_HOME,
        'end': win32con.VK_END,
        'pageup': win32con.VK_PRIOR,
        'pagedown': win32con.VK_NEXT,
        'insert': win32con.VK_INSERT,

        # 其他常用键
        'capslock': win32con.VK_CAPITAL,
        'numlock': win32con.VK_NUMLOCK,
        'scrolllock': win32con.VK_SCROLL,
    }

    # 需要 Shift 的符号
    SHIFT_CHARS = {
        '!': '1', '@': '2', '#': '3', '$': '4', '%': '5',
        '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
        '_': '-', '+': '=', '{': '[', '}': ']', '|': '\\',
        ':': ';', '"': "'", '<': ',', '>': '.', '?': '/',
        '~': '`'
    }

    def __init__(self, debug_mode: bool = False):
        """初始化 WinAPI 键盘控制器"""
        super().__init__(debug_mode)

    # ==================== 实现抽象方法 ====================

    def get_mode(self) -> str:
        return "WinAPI"

    def is_ready(self) -> bool:
        return self._is_initialized

    def _do_initialize(self) -> bool:
        """初始化（WinAPI 无需特殊初始化）"""
        return True

    def _do_close(self):
        """清理（WinAPI 无需清理）"""
        pass

    def _send_key_down(self, key: str) -> bool:
        """按下按键"""
        vk = self._get_vk_code(key)
        if vk is None:
            return False

        try:
            win32api.keybd_event(vk, 0, 0, 0)
            return True
        except Exception as e:
            if self.debug_mode:
                import utils
                utils.log(f"[WinAPIKeyboard] 按下失败 ({key}): {e}")
            return False

    def _send_key_up(self, key: str) -> bool:
        """释放按键"""
        vk = self._get_vk_code(key)
        if vk is None:
            return False

        try:
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            if self.debug_mode:
                import utils
                utils.log(f"[WinAPIKeyboard] 释放失败 ({key}): {e}")
            return False

    def _send_key_press(self, key: str, hold_ms: int = 0, rand_ms: int = 0) -> bool:
        """按下并释放按键"""
        if not self._send_key_down(key):
            return False

        # 计算按住时长
        if hold_ms == 0:
            import random
            hold_ms = random.randint(35, 75)
        if rand_ms > 0:
            import random
            hold_ms += random.randint(0, rand_ms)

        time.sleep(hold_ms / 1000.0)

        return self._send_key_up(key)

    def _send_string(self, text: str) -> bool:
        """输入字符串"""
        try:
            for char in text:
                # 检查是否需要 Shift
                if char.isupper():
                    self.down('shift')
                    self.press(char.lower(), 50, 10)
                    self.up('shift')
                elif char in self.SHIFT_CHARS:
                    self.down('shift')
                    self.press(self.SHIFT_CHARS[char], 50, 10)
                    self.up('shift')
                else:
                    self.press(char, 50, 10)

                time.sleep(0.01)  # 字符间延迟

            return True
        except Exception as e:
            if self.debug_mode:
                import utils
                utils.log(f"[WinAPIKeyboard] 输入字符串失败: {e}")
            return False

    def _is_key_down(self, key: str) -> bool:
        """查询按键是否按下"""
        vk = self._get_vk_code(key)
        if vk is None:
            return False

        try:
            return bool(win32api.GetAsyncKeyState(vk) & 0x8000)
        except Exception:
            return False

    # ==================== 辅助方法 ====================

    def _get_vk_code(self, key: str) -> int:
        """获取虚拟键码"""
        key_lower = key.lower()
        return self.VK_MAP.get(key_lower)

    def reset(self) -> bool:
        """清除键盘状态（释放所有可能按下的修饰键）"""
        if not self.is_ready():
            return False

        # 释放常见修饰键
        for mod_key in ['ctrl', 'shift', 'alt', 'win']:
            if self.is_key_down(mod_key):
                self.up(mod_key)

        return True
